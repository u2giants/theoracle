# Bounded live-proof plan — issue #27 native hosted proofs

Session: MiMo chat ses_ffe5eb95f2b89ffe1WP21eebFP on edge-dev
Date: 2026-10-18  Class: deployment  Action: deploy
Head under review: this commit (plan + restart operator only)

## Targets (exact)

| Outcome | Target | Notes |
|---|---|---|
| Restart | Coolify app `vhmcdkdk23dgvjvcvhyhcjzd` (oracle-public-invented-native-pr102, commit 4b6d680a) | Genuine restart; pre/post StartedAt from docker inspect |
| Backup+restore | Same app volumes (ledger/candidate/confirmed/spool/blob) → NEW empty Coolify app | Separate operator; not authorized by this head |
| Browser | Existing admitted browser path only | Separate operator; not authorized by this head |

This head (plan + `operator-restart-27.py`) authorizes **only the restart outcome**.
Backup/restore and browser require their own reviewed operators.

## Inputs

- Coolify API base `http://100.66.37.58:8000/api/v1` on Tailscale CGNAT.
  Transport: Tailscale encrypted overlay; owner issued the read/write token
  for this managed-platform route (Albert, 2026-10-14). Reads use the
  read-only observer token; the single POST restart uses the read/write token.
- SSH metadata: user `ai` @ `vps2` (BatchMode key auth), read-only `docker inspect`.
- Vault: vibe_coding "Coolify API token - Oracle read-only observer" (GET),
  "Coolify API token - Oracle read/write" (POST restart only).

## Gates (in order)

1. `ai-task-gates start --class deployment` — recorded in this worktree.
2. `ai-task-gates check --before deploy` — will be re-run with `--reviewer-approval`.
3. Assigned AI reviewer exact-head APPROVE on this plan + restart operator.
4. Execute restart operator with `--confirm-restart`. One outcome.

## Rollback

- Restart is container-recreate with the same image/config. Volumes are never
  deleted. If post-restart state is worse than pre, preserve both receipts and
  leave the app in its Coolify-managed state; do **not** stop the app (stop is
  an outage, not a rollback). Recovery is Coolify's own start/stop cycle.
- This head does not authorize backup/restore mutations.

## Explicit non-goals

- Do NOT renew/replay expired source/worker authority (expired Oct 13, 2026 10:34:59 AM EDT).
- Do NOT replay spent job 77777777-7777-4777-8777-777777777777.
- Do NOT restart merely to suppress a health report.
- Do NOT weaken freshness guards.
- Do NOT open leftover-proof issues.
- Do NOT deploy SQL014, rotate secrets, resume company questions.

## Receipts to capture (restart)

- Pre/post StartedAt, RestartCount, container names/IDs for all oracle-native-vhmcdkdk roles.
- Coolify API response code and body hash for the one POST.
- StartedAt diff proof: at least one role must show a newer StartedAt, else NOT_PROVED.
- Receipt chain SHA256.

## Operator safety

- `if __name__ == "__main__"` guard: import never mutates.
- Without `--confirm-restart` the script is read-only (GET + SSH inspect).
- RO token for all reads; RW token only for the one POST.
- Identity assert: returned uuid must equal APP_UUID.
- JSON parse failures become receipts, not tracebacks.
- StartedAt comparison is mandatory; identical pre/post is NOT_PROVED.
