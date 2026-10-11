#!/usr/bin/env python3
"""Read the private original inventory with strict, bounded admission."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import sys
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/oracle-brain"))
from oracle_brain.ingest.originals import (  # noqa: E402
    CallBudget, OpenAIVisualReader, ReadingProvenance, ReadingResponse,
    ReviewResponse, parser_identity, read_original,
)
from oracle_brain.provider_policy import ProcessingApproval, ProcessingRequest  # noqa: E402
from oracle_brain.provider_transport import transport_options  # noqa: E402

TEXT_TYPES = {"text/plain", "text/markdown"}
VISUAL_TYPES = {"image/png", "image/jpeg", "application/pdf"}
ALL_TYPES = TEXT_TYPES | VISUAL_TYPES


def _write_json(path: Path, value: object, *, exclusive: bool) -> None:
    flags = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if exclusive else os.O_TRUNC)
    with os.fdopen(os.open(path, flags, 0o600), "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True)


def _prevalidate(rows: object, originals: Path) -> dict[str, dict]:
    if not isinstance(rows, list) or not rows:
        raise ValueError("manifest must contain uploads")
    root = originals.resolve()
    groups: dict[str, dict] = {}
    source_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("manifest upload must be an object")
        try:
            source_id = str(UUID(str(row["source_id"])))
            declared_hash = str(row["sha256"])
            size = row["bytes"]
            content_type = str(row.get("file_type", row.get("content_type", "")))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("manifest upload is incomplete") from exc
        if source_id in source_ids:
            raise ValueError("manifest source IDs must be unique")
        source_ids.add(source_id)
        if len(declared_hash) != 64 or any(c not in "0123456789abcdef" for c in declared_hash):
            raise ValueError("manifest hash is invalid")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ValueError("manifest byte count is invalid")
        if content_type not in ALL_TYPES:
            raise ValueError("manifest content type is unsupported")
        original = originals / source_id
        if original.is_symlink() or original.resolve().parent != root:
            raise PermissionError("original outside protected inventory")
        data = original.read_bytes()
        actual_hash = hashlib.sha256(data).hexdigest()
        if len(data) != size or actual_hash != declared_hash:
            raise ValueError("original inventory changed")
        group = groups.setdefault(actual_hash, {"digest": actual_hash, "data": data,
                                                 "content_type": content_type, "source_ids": []})
        if group["content_type"] != content_type:
            raise ValueError("aliases for one original must have one content type")
        group["source_ids"].append(source_id)
    return groups


def _valid_cached(path: Path, group: dict, identity: str) -> dict | None:
    if not path.exists():
        return None
    if path.is_symlink():
        raise PermissionError("cached reading must not be a symlink")
    value = json.loads(path.read_text(encoding="utf-8"))
    provenance = ReadingProvenance.model_validate(value.get("provenance", {}))
    if provenance.original_hash != group["digest"] or provenance.parser_identity != identity:
        raise RuntimeError("existing reading does not match current parser")
    if provenance.content_type != group["content_type"]:
        raise RuntimeError("existing reading content type changed")
    text = value.get("text")
    if not isinstance(text, str) or hashlib.sha256(text.encode()).hexdigest() != provenance.content_hash:
        raise RuntimeError("existing reading content hash is invalid")
    reading = ReadingResponse.model_validate(value.get("reading", {}))
    review = ReviewResponse.model_validate(value.get("review", {}))
    if (not reading.complete or not review.complete_supported
            or [page.page_number for page in reading.pages] != list(range(1, provenance.page_count + 1))
            or review.checked_pages != list(range(1, provenance.page_count + 1))
            or any(not page.text.strip() or page.uncertainties for page in reading.pages)
            or review.unsupported or review.omissions or review.uncertainties):
        raise RuntimeError("existing reading has not passed current review")
    if provenance.evidence_kind == "native_text":
        if group["content_type"] not in TEXT_TYPES or text.encode("utf-8") != group["data"]:
            raise RuntimeError("existing native reading is not lossless")
        expected_receipt = hashlib.sha256((group["digest"] + ":strict-utf8-byte-roundtrip").encode()).hexdigest()
    else:
        if group["content_type"] in TEXT_TYPES:
            raise RuntimeError("existing evidence kind is invalid")
        expected_receipt = hashlib.sha256(review.model_dump_json().encode()).hexdigest()
    if provenance.review_receipt != expected_receipt:
        raise RuntimeError("existing review receipt is invalid")
    value["source_ids"] = list(group["source_ids"])
    return value


def _process_group(group: dict, output: Path, *, reader, reviewer,
                   reader_request: ProcessingRequest, reviewer_request: ProcessingRequest,
                   approvals: list[ProcessingApproval], reader_model: str,
                   reviewer_model: str, config_id: str) -> dict:
    digest = group["digest"]
    sequence = 0

    def callback(which):
        def invoke(prompt, views):
            nonlocal sequence
            sequence += 1
            try:
                raw = (reader if which == 0 else reviewer)(prompt, views)
            except Exception as error:
                import re
                code = getattr(error, "code", None)
                diagnostic = {"error_class": type(error).__name__,
                              "http_status": getattr(error, "status_code", None),
                              "code": code if isinstance(code,str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,80}",code) else None}
                _write_json(output / f"{digest}-call-{sequence}-model-{which}-error.json", diagnostic, exclusive=True)
                raise
            _write_json(output / f"{digest}-call-{sequence}-model-{which}.json",
                        {"response": raw}, exclusive=True)
            return raw
        return invoke

    budget = CallBudget() if group["content_type"] in VISUAL_TYPES else None
    result = read_original(
        data=group["data"], content_type=group["content_type"], expected_hash=digest,
        reader=callback(0), reviewer=callback(1), reader_request=reader_request,
        reviewer_request=reviewer_request, approvals=approvals, budget=budget,
        reader_model=reader_model, reviewer_model=reviewer_model, config_id=config_id,
    )
    provenance = ReadingProvenance(
        original_hash=digest,
        content_hash=hashlib.sha256(result.normalized_text.encode()).hexdigest(),
        parser_identity=result.parser_identity, content_type=group["content_type"],
        evidence_kind=("native_text" if group["content_type"] in TEXT_TYPES else "visual_transcription"),
        page_count=result.page_count, review_receipt=result.review_receipt,
    )
    value = {
        "source_ids": list(group["source_ids"]), "provenance": provenance.model_dump(),
        "text": result.normalized_text,
        "reading": result.reading.model_dump(mode="json", by_alias=True),
        "review": result.review.model_dump(mode="json"),
    }
    _write_json(output / f"{digest}.json", value, exclusive=True)
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--originals", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.is_symlink():
        raise PermissionError("private output must not be a symlink")
    args.output.mkdir(mode=0o700, parents=True, exist_ok=True)
    if args.output.stat().st_mode & 0o077:
        raise PermissionError("output must be private")

    # No environment admission or provider construction occurs before this check.
    rows = json.loads(args.manifest.read_text(encoding="utf-8"))
    groups = _prevalidate(rows, args.originals)
    visual_groups = [g for g in groups.values() if g["content_type"] in VISUAL_TYPES]

    config_id = os.environ.get("ORACLE2_ORIGINAL_CONFIG_ID", "native")
    reader_model = "native-reader"
    reviewer_model = "native-reviewer"
    empty_request = ProcessingRequest(provider="native", account="local", endpoint="local",
                                      data_classes=frozenset(), purpose="native", terms_hash="native")
    rr = vr = empty_request
    approvals: list[ProcessingApproval] = []
    readers = reviewers = None
    if visual_groups:
        reader_model = os.environ["ORACLE2_ORIGINAL_READER_MODEL"]
        reviewer_model = os.environ["ORACLE2_ORIGINAL_REVIEWER_MODEL"]
        requests = json.loads(os.environ["ORACLE2_ORIGINAL_PROCESSING_REQUESTS"])
        approvals = [ProcessingApproval.model_validate(x) for x in json.loads(os.environ["ORACLE2_PROCESSING_APPROVALS"])]
        endpoint = os.environ["ORACLE2_ORIGINAL_OPENAI_ENDPOINT"]
        rr, vr = (ProcessingRequest.model_validate(requests[k]) for k in ("reader", "reviewer"))
        if any(r.endpoint != endpoint for r in (rr, vr)):
            raise PermissionError("provider configuration differs from register")
        if rr.provider != vr.provider:
            raise PermissionError("reader and reviewer transports must match")
        from openai import OpenAI
        client = OpenAI(api_key=os.environ["ORACLE2_ORIGINAL_OPENAI_KEY"], base_url=endpoint,
                        timeout=360, max_retries=0)
        reader_transport = transport_options(rr, reader_model, operation="chat")
        reviewer_transport = transport_options(vr, reviewer_model, operation="chat")
        if rr.endpoint != vr.endpoint:
            raise PermissionError("reader and reviewer transports must match")
        readers = OpenAIVisualReader(client, reader_model, reader_transport)
        reviewers = OpenAIVisualReader(client, reviewer_model, reviewer_transport)
    identity = parser_identity(reader_model=reader_model, reviewer_model=reviewer_model, config_id=config_id)

    completed: dict[str, dict] = {}
    failures: list[dict] = []
    pending: list[dict] = []
    for group in groups.values():
        cached = _valid_cached(args.output / f"{group['digest']}.json", group, identity)
        if cached is None:
            if any(args.output.glob(f"{group['digest']}-call-*.json")):
                raise RuntimeError("partial reading requires a new reviewed attempt directory")
            pending.append(group)
        else:
            completed[group["digest"]] = cached

    def run(group):
        return _process_group(group, args.output, reader=readers, reviewer=reviewers,
                              reader_request=rr, reviewer_request=vr, approvals=approvals,
                              reader_model=reader_model, reviewer_model=reviewer_model,
                              config_id=config_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(run, group): group for group in pending}
        for future in as_completed(futures):
            group = futures[future]
            try:
                completed[group["digest"]] = future.result()
            except Exception as error:
                failures.append({"original_hash": group["digest"], "error_class": type(error).__name__})
                completed[group["digest"]] = {"source_ids": list(group["source_ids"]), "failed": True}
            progress = {
                "original_uploads": len(rows), "distinct_originals_processed": len(completed),
                "qualified_distinct_originals": sum(not v.get("failed", False) for v in completed.values()),
                "failures": failures, "complete": False,
            }
            _write_json(args.output / "summary.json", progress, exclusive=False)
            print(json.dumps({"finished_original": group["digest"], "complete": False}))

    aliases = {digest: list(group["source_ids"]) for digest, group in groups.items()}
    summary = {
        "original_uploads": len(rows), "distinct_originals_processed": len(groups),
        "qualified_distinct_originals": sum(not v.get("failed", False) for v in completed.values()),
        "failures": failures, "complete": not failures and len(completed) == len(groups),
        "aliases": aliases,
    }
    _write_json(args.output / "summary.json", summary, exclusive=False)
    print(json.dumps({k: v for k, v in summary.items() if k not in {"aliases", "failures"}}))
    return 0 if summary["complete"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"success": False, "error_class": type(error).__name__}))
        raise SystemExit(1)
