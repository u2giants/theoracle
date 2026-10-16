"""Industry source register; JSON-compatible YAML so no parser dependency is required."""
from dataclasses import dataclass
from datetime import timedelta
import json
from pathlib import Path

CADENCES = {'weekly': timedelta(days=7), 'quarterly': timedelta(days=91)}
ACCESS = {'public', 'licensed', 'member'}


@dataclass(frozen=True)
class Source:
    source_id: str
    publisher: str
    url: str
    jurisdiction: str
    scope: str
    access: str
    cadence: str
    enabled: bool = True
    rights_confirmed: bool = False

    def __post_init__(self):
        if self.cadence not in CADENCES:
            raise ValueError(f'unknown cadence {self.cadence!r}')
        if self.access not in ACCESS:
            raise ValueError(f'unknown access {self.access!r}')
        if not self.url.startswith('https://'):
            raise ValueError('source url must be https')
        for field in ('enabled', 'rights_confirmed'):
            if not isinstance(getattr(self, field), bool):
                raise ValueError(f'{field} must be a bool')
        for field in ('source_id', 'publisher', 'jurisdiction', 'scope'):
            if not isinstance(getattr(self, field), str) or not getattr(self, field).strip():
                raise ValueError(f'{field} must be a nonempty string')

    @property
    def interval(self) -> timedelta:
        return CADENCES[self.cadence]


def parse_register(text: str) -> tuple[Source, ...]:
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(text)
    except ImportError:
        data = json.loads(text)
    sources = tuple(Source(**row) for row in data['sources'])
    ids = [s.source_id for s in sources]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate source_id')
    return sources


def load_register(path: Path) -> tuple[Source, ...]:
    return parse_register(Path(path).read_text())
