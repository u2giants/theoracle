"""Tests for apps/brain/brain/colab_bakeoff.py (#664 Steps 1.3 & 2.2 -> #607 Step 2.3 bridge)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from brain.colab_bakeoff import build_bakeoff_attempts_from_colab, compute_ccu_economics
from brain.colab_packet import ColabPacketError, WindowSpec
from brain.extract.relations import KnownMention
from brain.intake.bakeoff import (
    ThreadMeta,
    claim_identity,
    score_candidate,
    select_winner,
)


def _make_window_spec(source_id: str, chunk_id: str, text: str) -> WindowSpec:
    known = [
        KnownMention(
            key="m1",
            mention_id=f"men-{chunk_id}-1",
            entity_type="Person",
            name="Jessica",
            normalized_name="jessica",
        ),
        KnownMention(
            key="m2",
            mention_id=f"men-{chunk_id}-2",
            entity_type="Artifact",
            name="Disney style guide",
            normalized_name="disney style guide",
        ),
    ]
    return WindowSpec(
        source_id=source_id,
        chunk_id=chunk_id,
        window=[(chunk_id, text, [])],
        known=known,
        prompt=f"PASSAGE:\n<<<\n{text}\n>>>",
    )


def test_colab_bakeoff_conversion_preserves_first_attempt_truncation_and_scores_cleanly(
    tmp_path: Path,
) -> None:
    """First-attempt truncations recovered at 4000 tokens still register first_status='truncated'."""
    p_hash = "hash-step13-test"
    text_a = "Jessica approves the Disney style guide every Tuesday."
    text_b = "Jessica sends the Disney style guide to packaging."

    spec_a = _make_window_spec("src-1", "chk-1", text_a)
    spec_b = _make_window_spec("src-2", "chk-2", text_b)

    pkt_rows = [
        {
            "packet_version": 1,
            "source_id": "src-1",
            "chunk_id": "chk-1",
            "prompt_hash": p_hash,
            "max_tokens": 2000,
            "known_keys": ["m1", "m2"],
            "prompt": spec_a.prompt,
        },
        {
            "packet_version": 1,
            "source_id": "src-2",
            "chunk_id": "chk-2",
            "prompt_hash": p_hash,
            "max_tokens": 2000,
            "known_keys": ["m1", "m2"],
            "prompt": spec_b.prompt,
        },
    ]
    pkt_bytes = ("\n".join(json.dumps(r) for r in pkt_rows) + "\n").encode("utf-8")
    pkt_path = tmp_path / "tuning50.jsonl"
    pkt_path.write_bytes(pkt_bytes)
    (tmp_path / "tuning50.jsonl.manifest.json").write_text(
        json.dumps(
            {
                "packet_version": 1,
                "sha256": hashlib.sha256(pkt_bytes).hexdigest(),
                "item_count": 2,
                "prompt_hash": p_hash,
                "source_ids": ["src-1", "src-2"],
            }
        ),
        encoding="utf-8",
    )

    reply_a = {
        "relations": [
            {
                "from": "m1",
                "to": "m2",
                "type": "PERFORMS",
                "description": "Jessica approves the Disney style guide.",
                "description_en": "",
                "stance": "practice",
                "confidence": 0.96,
                "quote": text_a,
            }
        ],
        "new_mentions": [],
    }
    reply_b = {
        "relations": [
            {
                "from": "m1",
                "to": "m2",
                "type": "HANDS_OFF_TO",
                "description": "Jessica sends the Disney style guide.",
                "description_en": "",
                "stance": "practice",
                "confidence": 0.94,
                "quote": text_b,
            }
        ],
        "new_mentions": [],
    }

    model_tag = "Qwen/Qwen2.5-32B-Instruct@0123456789abcdef0123456789abcdef01234567"
    res_rows = [
        {
            "chunk_id": "chk-1",
            "prompt_hash": p_hash,
            "model_tag": model_tag,
            "raw_content": json.dumps(reply_a),
            "first_finish_reason": "stop",
            "finish_reason": "stop",
            "retried": False,
            "elapsed_ms": 400.0,
        },
        {
            # Truncated at 2000 tokens on first try, succeeded at 4000 tokens on retry!
            "chunk_id": "chk-2",
            "prompt_hash": p_hash,
            "model_tag": model_tag,
            "raw_content": json.dumps(reply_b),
            "first_finish_reason": "length",
            "finish_reason": "stop",
            "retried": True,
            "elapsed_ms": 800.0,
        },
    ]
    res_path = tmp_path / "results.jsonl"
    res_path.write_text("\n".join(json.dumps(r) for r in res_rows) + "\n", encoding="utf-8")

    conv = build_bakeoff_attempts_from_colab(
        pkt_path,
        res_path,
        gpu_tier="A100",
        wall_seconds=18.0,
        windows_by_chunk={"chk-1": spec_a, "chk-2": spec_b},
        thread_id_by_source={"src-1": "thr-1", "src-2": "thr-2"},
        expected_prompt_hash=p_hash,
    )
    assert conv.model_tag == f"colab-vllm/{model_tag}"
    assert len(conv.attempts) == 2
    assert conv.attempts[0].first_status == "ok"
    assert conv.attempts[0].final_status == "ok"
    assert conv.attempts[1].first_status == "truncated"
    assert conv.attempts[1].final_status == "ok"
    assert conv.attempts[0].cost_usd == 0.0
    # 18s on A100 (15 CCU/hr) = 0.075 CCU across 2 passages = 37.5 CCU / 1000 passages
    assert conv.ccu_spent_estimate == pytest.approx(0.075)
    assert conv.ccu_per_1000_passages == pytest.approx(37.5)

    meta = {
        "thr-1": ThreadMeta("thr-1", "email", 1),
        "thr-2": ThreadMeta("thr-2", "teams", 2),
    }
    cid_a = claim_identity(
        "thr-1",
        "Jessica",
        "PERFORMS",
        "Disney style guide",
        text_a,
        "practice",
        "Jessica approves the Disney style guide.",
    )
    cid_b = claim_identity(
        "thr-2",
        "Jessica",
        "HANDS_OFF_TO",
        "Disney style guide",
        text_b,
        "practice",
        "Jessica sends the Disney style guide.",
    )
    score = score_candidate(
        conv.model_tag,
        conv.attempts,
        meta,
        {cid_a: "keep", cid_b: "keep"},
        {"thr-1": {"g1"}, "thr-2": {"g2"}},
        {cid_a: ["g1"], cid_b: ["g2"]},
        truncation_upper_override=0.0078,
        bootstrap_resamples=200,
    )
    assert score.first_truncation_threads == 1
    assert score.passages_usable == 2
    assert score.usd_per_1000_passages == 0.0
    assert score.passes_gates is True
    assert select_winner([score]) == score


def test_colab_bakeoff_rejects_incomplete_or_mixed_model_results(tmp_path: Path) -> None:
    """Missing chunks or mixed model tags in a single bakeoff run abort loudly."""
    p_hash = "hash-guard"
    spec = _make_window_spec("src-1", "chk-1", "Jessica approves the Disney style guide.")
    pkt_bytes = (
        json.dumps(
            {
                "packet_version": 1,
                "source_id": "src-1",
                "chunk_id": "chk-1",
                "prompt_hash": p_hash,
                "max_tokens": 2000,
                "known_keys": ["m1", "m2"],
                "prompt": spec.prompt,
            }
        )
        + "\n"
    ).encode("utf-8")
    pkt_path = tmp_path / "pkt.jsonl"
    pkt_path.write_bytes(pkt_bytes)
    (tmp_path / "pkt.jsonl.manifest.json").write_text(
        json.dumps(
            {
                "packet_version": 1,
                "sha256": hashlib.sha256(pkt_bytes).hexdigest(),
                "item_count": 1,
                "prompt_hash": p_hash,
                "source_ids": ["src-1"],
            }
        ),
        encoding="utf-8",
    )
    empty_res = tmp_path / "empty_res.jsonl"
    empty_res.write_text("", encoding="utf-8")

    with pytest.raises(ColabPacketError, match="missing 1 packet chunk"):
        build_bakeoff_attempts_from_colab(
            pkt_path,
            empty_res,
            windows_by_chunk={"chk-1": spec},
            expected_prompt_hash=p_hash,
        )

    ccu_spent, per_k = compute_ccu_economics(gpu_tier="L4", wall_seconds=360.0, passage_count=500)
    assert ccu_spent == pytest.approx(0.2)
    assert per_k == pytest.approx(0.4)
