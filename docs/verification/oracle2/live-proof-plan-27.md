<!-- Privacy rendering: infrastructure references are non-executable publication placeholders. Original Git blob b06386a48efda4c64798c9260ebbe4405a89857a at ab73ef791ad48f187fa5d2998428aec99ce6bd82; exact originals are retained in the #27 private custody archive. No obligations, authority, timing or acceptance are changed. -->
# Bounded live-proof plan — issue #27 native hosted proofs

Session: MiMo chat ses_ffe5eb95f2b89ffe1WP21eebFP on edge-dev
Date: 2026-10-18  Class: deployment  Action: deploy

## Targets (exact)

| Outcome | Target | Operator | Status |
|---|---|---|---|
| Restart | Coolify app `vhmcdkdk23dgvjvcvhyhcjzd` | `operator-restart-27.py` | PROVED 2026-10-18 |
| Backup+restore | 5 data volumes of same app → new `-restore27` volumes | `operator-backup-restore-27.py` | this head |
| Browser | native gateway mTLS; no browser FQDN | (read-only check) | recorded |

This head authorizes **restart (already proved) and backup+restore**.
Browser is a read-only fact-finding outcome (no mutation).

## Inputs

- Coolify API `http://PRIVATE_HOST_SHA256_69e08d69438f83a96aefc4a9f82450e9244100f6db11b1e2cae8f3b956f054ae:8000/api/v1` on Tailscale CGNAT (encrypted overlay).
  Owner issued RW token for this managed-platform route (Albert, 2026-10-14).
  Reads use RO observer token; the one POST restart used RW token.
- SSH metadata: user `ai` @ `vps2` (BatchMode key auth), read-only inspect +
  bounded volume backup/restore to NEW volumes only.
- Vault: vibe_coding "Coolify API token - Oracle read-only observer" (GET),
  "Coolify API token - Oracle read/write" (POST restart only).

## Gates

1. `ai-task-gates start --class deployment` — recorded.
2. `ai-task-gates check --before deploy --reviewer-approval <report>` — required before each mutation batch.
3. Assigned AI reviewer exact-head APPROVE (Muse, implementer mimo) with local tests.
4. Execute one bounded outcome per action.

## Backup/restore safety (this head)

- Source volumes mounted `:ro` only. Never mutated.
- Staging dir created atomically with mode 700 via `mkdir -m 700` after
  exists/symlink refusal (`mk_staging`). Tars `chmod 600`.
- Restore target volumes named `*-restore27`; refused if already exist
  (no `docker volume rm`).
- Verification is per-file sha256 manifest compare (source vs restored),
  not just file counts. Hash format validated (`^[0-9a-f]{64}$`).
- Helper image pinned to tag `alpine:3.20` and all outputs hash-checked.
  (Full digest pin optional; manifest compare is the integrity control.)
- Rollback: source untouched; failed restore targets left in place for
  inspection or manually removed (named `-restore27` only).

## Restart safety (already executed)

- Pre/post StartedAt captured via SSH docker inspect.
- All 18 roles restarted: StartedAt moved from 2026-10-13T13:53:xxZ to
  2026-10-18T13:08:49-58Z. Deployment UUID `jyzwe2cezkcbsxuy394muibt`.
- No authority renewal, no job replay.

## Browser fact

- All Oracle native Coolify apps have `fqdn: null` (no domain).
- Historical gateway `oracle-native-acceptance.178.156.180.212.sslip.io`
  resolves but HTTPS requires mTLS client certificate
  (`tlsv13 alert certificate required`). HTTP returns 404.
- No authenticated browser surface exists for the native hosted installation.
  Historical PR96 browser login is the web application (Vercel/Postgres),
  not this native gateway. Recorded as fact; not a mutation.

## Explicit non-goals

- Do NOT renew/replay expired source/worker authority (expired Oct 13, 2026 10:34:59 AM EDT).
- Do NOT replay spent job 77777777-7777-4777-8777-777777777777.
- Do NOT restart merely to suppress a health report.
- Do NOT weaken freshness guards.
- Do NOT open leftover-proof issues.
- Do NOT deploy SQL014, rotate secrets, resume company questions.
