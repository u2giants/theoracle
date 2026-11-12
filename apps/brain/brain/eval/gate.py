"""Live quality gate for eval runs (repair plan §9 Phase B, step B3).

``decide()`` compares one eval run with the last accepted one and fails when
the mean drops more than 0.05 or any question errored. A passing run is
marked ``accepted`` in ``cmap.eval_run`` and becomes the baseline for the
next run; with no previous accepted run the drop check is skipped. No model
calls happen here — ``brain.eval.run`` produces the run, this module only
compares means and error flags (the new score, not ``score_legacy``).

``python -m brain.eval.gate`` gates the latest stored run (preview/local).
``python -m brain.eval.gate --live`` queues one eval on the deployed brain
(``BRAIN_BASE_URL`` with the shared token in ``BRAIN_SHARED_TOKEN``, sent as
``x-brain-token`` like the web proxy), waits for the run to land and applies
the same rule; ``.github/workflows/brain-quality.yml`` runs this after every
verified deploy and nightly.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from brain.db import get_pool

logger = logging.getLogger(__name__)

GATE_DROP = 0.05
LIVE_ATTEMPTS = 60
LIVE_INTERVAL_SECONDS = 20.0
HTTP_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class GateDecision:
    """The gate's verdict on one eval run."""

    passed: bool
    reason: str
    run_id: str | None = None
    mean_score: float | None = None
    previous_mean: float | None = None
    drop: float | None = None
    error_count: int = 0


def _question_errors(run: Mapping[str, Any]) -> list[str]:
    """Error texts recorded on a run's questions (B2 ``results`` shape)."""
    return [
        str(item.get("error"))
        for item in run.get("results") or []
        if item.get("error")
    ]


def decide(
    latest: Mapping[str, Any], last_accepted: Mapping[str, Any] | None
) -> GateDecision:
    """FAIL when the mean drops more than 0.05 or any question errored."""
    mean = float(latest.get("mean_score") or 0.0)
    errors = _question_errors(latest)
    run_id = str(latest.get("id") or "") or None
    previous_mean = (
        None
        if last_accepted is None
        else float(last_accepted.get("mean_score") or 0.0)
    )
    drop = None if previous_mean is None else round(previous_mean - mean, 4)
    if errors:
        return GateDecision(
            passed=False,
            reason=f"{len(errors)} question error(s): {'; '.join(errors)}",
            run_id=run_id,
            mean_score=mean,
            previous_mean=previous_mean,
            drop=drop,
            error_count=len(errors),
        )
    if drop is not None and drop > GATE_DROP:
        return GateDecision(
            passed=False,
            reason=f"mean dropped {drop}, more than {GATE_DROP}",
            run_id=run_id,
            mean_score=mean,
            previous_mean=previous_mean,
            drop=drop,
        )
    reason = "first run, no accepted baseline" if drop is None else "mean held"
    return GateDecision(
        passed=True,
        reason=reason,
        run_id=run_id,
        mean_score=mean,
        previous_mean=previous_mean,
        drop=drop,
    )


def run_gate() -> GateDecision:
    """Gate the newest stored run and mark it accepted when it passes."""
    with get_pool().connection() as conn:
        row = conn.execute(
            "SELECT id::text, created_at, mean_score, results "
            "FROM cmap.eval_run ORDER BY created_at DESC, id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return GateDecision(passed=False, reason="no eval run to gate")
        latest = {"id": row[0], "mean_score": row[2], "results": row[3]}
        prior = conn.execute(
            "SELECT id::text, mean_score, results FROM cmap.eval_run "
            "WHERE accepted AND (created_at, id) < (%s::timestamptz, %s::uuid) "
            "ORDER BY created_at DESC, id DESC LIMIT 1",
            (row[1], row[0]),
        ).fetchone()
        last_accepted = (
            None
            if prior is None
            else {"id": prior[0], "mean_score": prior[1], "results": prior[2]}
        )
        decision = decide(latest, last_accepted)
        if decision.passed:
            conn.execute(
                "UPDATE cmap.eval_run SET accepted = true WHERE id = %s",
                (row[0],),
            )
        conn.commit()
    logger.info("gate %s run=%s: %s", "PASS" if decision.passed else "FAIL", row[0], decision.reason)
    return decision


def _run_payload(base: str, headers: dict[str, str]) -> dict[str, Any]:
    response = httpx.get(
        f"{base}/eval/runs",
        headers=headers,
        params={"limit": 100},
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return dict(response.json())


def live_gate(
    base: str,
    token: str,
    attempts: int = LIVE_ATTEMPTS,
    interval: float = LIVE_INTERVAL_SECONDS,
) -> GateDecision:
    """Queue one eval on the deployed brain, wait for its run, gate it."""
    headers = {"x-brain-token": token}
    try:
        before = {str(run.get("id")) for run in _run_payload(base, headers).get("runs") or []}
        response = httpx.post(
            f"{base}/eval/run", headers=headers, timeout=HTTP_TIMEOUT_SECONDS
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return GateDecision(passed=False, reason=f"eval endpoint error: {exc}")
    logger.info("live gate: eval queued=%s", response.json().get("queued"))
    deadline = time.monotonic() + attempts * interval
    while time.monotonic() < deadline:
        time.sleep(interval)
        try:
            payload = _run_payload(base, headers)
        except httpx.HTTPError as exc:
            return GateDecision(passed=False, reason=f"run list error: {exc}")
        runs = list(payload.get("runs") or [])
        for position, run in enumerate(runs):
            if str(run.get("id")) in before:
                continue
            last_accepted = next(
                (item for item in runs[position + 1 :] if item.get("accepted")),
                None,
            )
            return decide(run, last_accepted)
        job = payload.get("latest_job") or {}
        if job.get("state") == "failed":
            return GateDecision(
                passed=False,
                reason=f"eval job failed: {job.get('error') or 'no error text'}",
            )
    return GateDecision(passed=False, reason="timed out waiting for the eval run")


def _summary(decision: GateDecision) -> str:
    head = "gate PASS" if decision.passed else "gate FAIL"
    parts = [f"{head}: {decision.reason}"]
    if decision.run_id:
        parts.append(f"run {decision.run_id}")
    if decision.mean_score is not None:
        parts.append(f"mean {decision.mean_score}")
    if decision.previous_mean is not None:
        parts.append(
            f"last accepted mean {decision.previous_mean} (drop {decision.drop})"
        )
    return " | ".join(parts)


def main(argv: list[str] | None = None) -> int:
    """Shell entry point: ``python -m brain.eval.gate [--live]``."""
    parser = argparse.ArgumentParser(
        description="Gate the Company Map eval runs (mean drop > 0.05 or errors fail)."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="queue a run on the deployed brain and gate it (BRAIN_BASE_URL)",
    )
    args = parser.parse_args(argv)
    if args.live:
        base = (os.environ.get("BRAIN_BASE_URL") or "").rstrip("/")
        token = os.environ.get("BRAIN_SHARED_TOKEN") or ""
        if not base or not token:
            print("BRAIN_BASE_URL and BRAIN_SHARED_TOKEN are required with --live")
            return 1
        decision = live_gate(base, token)
    else:
        decision = run_gate()
    print(_summary(decision))
    return 0 if decision.passed else 1


if __name__ == "__main__":
    sys.exit(main())
