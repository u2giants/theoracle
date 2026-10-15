"""Per-source processing limits for structural ingestion.

Offline S04 building block: bounded bytes, bounded blocks and a bounded
repair budget so a hostile or broken source fails visibly instead of looping.
"""
from __future__ import annotations

from dataclasses import dataclass, field

MAX_SOURCE_BYTES = 25 * 1024 * 1024
MAX_BLOCKS = 5_000
MAX_REPAIR_ATTEMPTS = 2

_ENCRYPTION_MARKERS = (b"/Encrypt", b"EncryptedPackage", b"\xd0\xcf\x11\xe0")


class SourceRejected(ValueError):
    """Terminal, user-visible ingestion failure; never retried silently."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


@dataclass
class ProcessingBudget:
    max_blocks: int = MAX_BLOCKS
    max_repairs: int = MAX_REPAIR_ATTEMPTS
    blocks: int = 0
    repairs: int = 0
    log: list[str] = field(default_factory=list)

    def take_block(self) -> None:
        self.blocks += 1
        if self.blocks > self.max_blocks:
            raise SourceRejected("block_budget_exhausted", str(self.max_blocks))

    def take_repair(self, why: str) -> None:
        self.repairs += 1
        self.log.append(why)
        if self.repairs > self.max_repairs:
            raise SourceRejected("repair_budget_exhausted", why)


def check_bytes(data: bytes, *, max_bytes: int = MAX_SOURCE_BYTES) -> None:
    if not data:
        raise SourceRejected("empty_source")
    if len(data) > max_bytes:
        raise SourceRejected("source_too_large", f"{len(data)} > {max_bytes}")
    if any(marker in data[:4096] for marker in _ENCRYPTION_MARKERS):
        raise SourceRejected("encrypted_source")


def decode_text(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SourceRejected("corrupt_source", "not valid UTF-8") from error
