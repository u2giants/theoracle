"""Durable interview state. Turns are idempotent so resume never replays accepted effects."""
from dataclasses import asdict, dataclass, field
import json
from typing import Optional


@dataclass
class Turn:
    turn_id: str
    need_key: str
    answer: Optional[str]  # None means "I don't know"
    language: str = 'en'
    speaker: str = 'employee'
    corrects: Optional[str] = None


@dataclass
class InterviewState:
    interview_id: str
    known: dict = field(default_factory=dict)
    asked: list = field(default_factory=list)
    declined: list = field(default_factory=list)
    turns: list = field(default_factory=list)
    applied_effects: list = field(default_factory=list)

    def record_question(self, need_key: str) -> bool:
        if need_key in self.asked:
            return False
        self.asked.append(need_key)
        return True

    def apply_turn(self, turn: Turn) -> bool:
        """Return False (no effect) when the turn was already accepted."""
        if turn.turn_id in self.applied_effects:
            return False
        self.applied_effects.append(turn.turn_id)
        self.turns.append(turn)
        if turn.speaker != 'employee':
            return True  # assistant statements are never evidence
        field_name = turn.need_key.split(':', 1)[1]
        if turn.answer is None:
            self.declined.append(turn.need_key)
        else:
            self.known[field_name] = turn.answer
        return True

    def dumps(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)

    @classmethod
    def loads(cls, raw: str) -> 'InterviewState':
        data = json.loads(raw)
        data['turns'] = [Turn(**t) for t in data['turns']]
        return cls(**data)
