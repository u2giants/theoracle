"""Sole externally appointed schema3 admission registry CONSUMER.

Returned hashes confer independent admission trust only. They never confer source
read, SQL/compiler/model/serve authority. No issuer, signing or auto-adoption.
"""
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from uuid import UUID

from .contracts import canonical_bytes, digest

PURPOSE = "captured-assembly-semantic-admission-v3"
HASH = re.compile(r"^[0-9a-f]{64}$")
MAX_BYTES = 1_048_576


def _require(condition, message):
    if not condition:
        raise PermissionError(message)


def _aware(value):
    _require(type(value) is str, "aware registry time required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise PermissionError("invalid registry time") from error
    _require(parsed.tzinfo is not None and parsed.utcoffset() is not None, "aware registry time required")
    return parsed


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate registry field")
        result[key] = value
    return result


@dataclass(frozen=True)
class SemanticRegistryAppointmentV3:
    """Expected EXTERNAL pins supplied by protected startup, never registry body."""
    workspace_id: UUID
    runtime_hash: str
    compiler_profile: str
    issuer_actor: UUID
    reviewer_actor: UUID
    valid_from: datetime
    expires_at: datetime
    purpose: str = PURPOSE

    def validate(self, now):
        _require(type(now) is datetime and now.tzinfo is not None and now.utcoffset() is not None,
                 "actual aware current time required")
        _require(type(self.workspace_id) is UUID and type(self.issuer_actor) is UUID
                 and type(self.reviewer_actor) is UUID and self.issuer_actor != self.reviewer_actor
                 and self.purpose == PURPOSE and self.compiler_profile == "candidate-compiler"
                 and type(self.runtime_hash) is str and HASH.fullmatch(self.runtime_hash),
                 "external schema3 appointment unavailable")
        _require(all(type(t) is datetime and t.tzinfo is not None and t.utcoffset() is not None
                     for t in (self.valid_from, self.expires_at))
                 and self.valid_from <= now < self.expires_at, "external appointment not current")

    def scope(self):
        return {"qualification_purpose": self.purpose, "workspace_id": str(self.workspace_id),
                "runtime_hash": self.runtime_hash, "compiler_profile": self.compiler_profile,
                "issuer_actor": str(self.issuer_actor), "reviewer_actor": str(self.reviewer_actor)}


class CurrentSemanticAdmissionsV3:
    def __init__(self, protected_registry_path, expected_external_registry_sha256, *, appointment):
        self.path = Path(protected_registry_path)
        _require(self.path.is_absolute() and self.path.parent.resolve() == self.path.parent,
                 "canonical protected semantic registry required")
        _require(type(expected_external_registry_sha256) is str
                 and HASH.fullmatch(expected_external_registry_sha256)
                 and type(appointment) is SemanticRegistryAppointmentV3,
                 "external startup registry pins required")
        self.expected_hash = expected_external_registry_sha256
        self.appointment = appointment

    def current(self, now):
        self.appointment.validate(now)
        _require(self.path.parent.resolve() == self.path.parent, "registry parent changed")
        with os.fdopen(os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
            before = os.fstat(stream.fileno())
            _require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid()
                     and before.st_nlink == 1 and before.st_mode & 0o077 == 0
                     and 0 < before.st_size <= MAX_BYTES, "unsafe external semantic registry")
            raw = stream.read(MAX_BYTES + 1)
            identity = lambda info: (info.st_dev, info.st_ino, info.st_mode, info.st_uid,
                                    info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            _require(len(raw) <= MAX_BYTES and identity(before) == identity(os.fstat(stream.fileno()))
                     == identity(self.path.lstat()), "external semantic registry mutated")
        _require(hashlib.sha256(raw).hexdigest() == self.expected_hash, "external semantic registry hash changed")
        try:
            row = json.loads(raw, object_pairs_hook=_unique,
                             parse_constant=lambda _: (_ for _ in ()).throw(PermissionError("nonfinite registry")))
        except (ValueError, UnicodeDecodeError) as error:
            raise PermissionError("invalid external semantic registry") from error
        scope = self.appointment.scope()
        fields = {"schema_version", "valid_from", "expires_at", "revoked", "admissions"} | set(scope)
        _require(type(row) is dict and set(row) == fields and type(row["schema_version"]) is int
                 and row["schema_version"] == 3 and all(row[k] == v for k, v in scope.items())
                 and row["revoked"] is False, "wrong or revoked semantic registry appointment")
        _require(self.appointment.valid_from <= _aware(row["valid_from"]) <= now
                 < _aware(row["expires_at"]) <= self.appointment.expires_at,
                 "semantic registry not current")
        _require(type(row["admissions"]) is list and len(row["admissions"]) <= 4096,
                 "bounded external admission metadata required")
        admitted = set()
        for item in row["admissions"]:
            _require(type(item) is dict and set(item) == {"schema_version", "admission_hash", "record_seal",
                     "valid_from", "expires_at", "revoked"} | set(scope), "fixed schema3 metadata only")
            _require(type(item["schema_version"]) is int and item["schema_version"] == 3
                     and all(item[k] == v for k, v in scope.items()) and item["revoked"] is False
                     and type(item["admission_hash"]) is str and HASH.fullmatch(item["admission_hash"])
                     and item["admission_hash"] not in admitted, "wrong/revoked/duplicate admission metadata")
            core = {k: v for k, v in item.items() if k != "record_seal"}
            _require(type(item["record_seal"]) is str and item["record_seal"] == digest(core),
                     "external admission record seal differs")
            _require(_aware(row["valid_from"]) <= _aware(item["valid_from"]) <= now
                     < _aware(item["expires_at"]) <= _aware(row["expires_at"]),
                     "external admission not current")
            admitted.add(item["admission_hash"])
        return frozenset(admitted)
