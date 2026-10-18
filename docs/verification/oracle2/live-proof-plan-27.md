# Bounded live-proof plan — issue #27 native hosted proofs
# Session: MiMo chat ses_ffe5eb95f2b89ffe1WP21eebFP on edge-dev
# Date: 2026-10-18
# Class: deployment  Action: deploy (Coolify managed-platform restart / app operations)
#
# TARGETS (exact):
#   Restart:       app vhmcdkdk23dgvjvcvhyhcjzd (oracle-public-invented-native-pr102, commit 4b6d680a)
#   Backup source: same app's volumes (ledger/candidate/confirmed/spool/blob)
#   Restore dest:  NEW empty Coolify compose app (fresh UUID), isolated namespace
#   Browser:       existing admitted browser path only; no new accounts
#
# INPUTS:
#   - Coolify API base http://100.66.37.58:8000/api/v1
#   - Read/write token: vault vibe_coding "Coolify API token - Oracle read/write"
#   - Read-only token:  vault vibe_coding "Coolify API token - Oracle read-only observer"
#   - SSH metadata: user ai @ vps2 (read-only docker inspect)
#
# GATES (in order):
#   1. ai-task-gates start --class deployment           [DONE]
#   2. ai-task-gates check --before deploy              [pending]
#   3. assigned AI reviewer exact-head APPROVE on this plan + operator [pending]
#   4. Execute one bounded outcome per action
#
# ROLLBACK:
#   - Restart: Coolify restart is self-rollback; containers return to same image/config.
#     Capture pre-restart StartedAt; if post-restart state is worse, stop the app
#     (Coolify stop) and preserve both receipts. Never delete volumes.
#   - Backup/restore: source volumes are never mutated. Restore target is a NEW
#     empty app; if restore fails, delete only the empty target. Source intact.
#   - Browser: read-only; no rollback needed.
#
# EXPLICIT NON-GOALS:
#   - Do NOT renew/replay expired source/worker authority (expired Oct 13 10:34:59 AM EDT)
#   - Do NOT replay spent job 77777777-7777-4777-8777-777777777777
#   - Do NOT restart merely to suppress health report
#   - Do NOT weaken freshness guards
#   - Do NOT open leftover-proof issues
#   - Do NOT deploy SQL014, rotate secrets, resume company questions
#
# RECEIPTS TO CAPTURE:
#   - Pre/post StartedAt, RestartCount, container IDs for all 18 roles
#   - Coolify API response codes and deployment UUIDs
#   - Backup manifest SHA256 per volume; restore verification counts
#   - Browser surface inventory (present/absent + reason)
