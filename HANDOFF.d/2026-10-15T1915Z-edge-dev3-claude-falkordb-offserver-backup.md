---
issue: 27
status: OPEN
owner: Claude chat 96374819-a928-4376-adda-01e214e6680b (edge-dev3)
---

# FalkorDB off-server backup done; S03 live proof continues on #27

## 0. ⚠️ BUSINESS DECISIONS ONLY THE OWNER CAN MAKE
- Staff review (Ilona, Jessica, others) comes LAST, after all of S03–S16 is built ([#58](https://github.com/u2giants/theoracle/issues/58), deferred).
- Company questions, reports, employee messages and grading on #27 stay PAUSED until Albert renews approval (it expired October 13).
- Backrest credentials: owner directive (Albert, October 15): "we're not rotating them". Do not rotate.

## 1. What this application is
The Oracle ([u2giants/theoracle](https://github.com/u2giants/theoracle)) is an evidence-backed company consultant being rebuilt in stages S01–S16 under parent [#24](https://github.com/u2giants/theoracle/issues/24). S03 is [#27](https://github.com/u2giants/theoracle/issues/27).

## 2. What we set out to do
Finish the FalkorDB leftovers from [the deploy handoff](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-10-15T1200Z-edge-dev3-claude-falkordb-coolify-deploy.md): the DNS rollback item, a nightly off-server copy of both FalkorDB databases, and a restore from it.

## 3. Current state
- #27 body now lists: the rollback step (remove DNS record oracle-graph.designflow.app, Cloudflare id 32019fc3aeb47e529ba7287cb0c84b2e) and the off-server backup item.
- Off-server copy: the existing Backrest on hetz (`/opt/backrest`, plan `docker-volumes`, every 15 min) already ships both `oracle-falkordb-*-backups` volumes to the restic repo on DigitalOcean Spaces nyc3 (bucket `backrest`). Nothing new was built.
- Restore from that copy PASSED for both roles (snapshot 191f367a; byte-identical to hetz). Receipt: [#27 comment](https://github.com/u2giants/theoracle/issues/27#issuecomment-6199759934).
- Plan updated: [PR #128](https://github.com/u2giants/theoracle/pull/128), merge 3f0cdcd, [plan §8](https://github.com/u2giants/theoracle/blob/main/docs/implementation/falkordb-coolify-deploy-plan.md).
- The graphs hold no data yet (restored DBSIZE 0), so the restore proved format and integrity, not content.

## 4. What did NOT work
- Running restic restore on the Backrest droplet (167.172.245.66): 458 MB RAM, stalled more than 18 minutes. Killed it and ran the restore on edge-dev3 instead (18 seconds).
- Reading live DBSIZE on hetz: the FalkorDB listeners are TLS-only, and the `hc`/`backup` users can only run PING/BGSAVE/LASTSAVE. Compared file hashes instead.
- Password SSH: the AI may not sign in with passwords. The `hetz-ai-ssh` item is a password.

## 5. Key findings
- SSH access works with the 1Password item "916-alien SSH key" (`op://vibe_coding/916-alien SSH key/private key?ssh-format=openssh`): hetz as `ai@178.156.180.212 -p 1904` (passwordless sudo), and the droplet as `root@167.172.245.66`.
- Restic repo credentials: the `do-spaces-backup` repo entry in `/opt/backrest/config/config.json` on hetz. Stream them, never print them.
- Restic snapshot times display in EDT.

## 6. Exact next steps
1. Continue S03's remaining live proof from #27's latest comments and body checklists (restart, fresh-instance backup/restore, native/browser integration, W10–W12).
2. Once the graphs hold real data, repeat the off-server restore and compare graph counts (checklist item on #27).

## 7. Constraints
No staff review before S03–S16 is done. Pushes go through a PR. Every Coolify mutation needs an AI-reviewer exact-plan APPROVE.

## 8. Access
edge-dev3 runs the tests. The vault is `vibe_coding`. SSH details are in §5.

## 9. Open risks
The droplet can't serve restores. Use any machine with at least 2 GB of RAM.

Posted by Claude chat 96374819-a928-4376-adda-01e214e6680b on edge-dev3
