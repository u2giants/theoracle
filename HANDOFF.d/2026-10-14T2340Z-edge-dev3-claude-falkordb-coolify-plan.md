---
issue: 27
status: OPEN
owner: claude (s02-coordination-pr-gates-baf147 worktree)
---

# FalkorDB-on-Coolify deploy plan (DRAFT, not executed)

## 0. BUSINESS DECISIONS ONLY THE OWNER CAN MAKE
Hetzner Cloud firewall token (read/write) if the firewall must be confirmed; otherwise none.

## State
- Plan: `docs/implementation/falkordb-coolify-deploy-plan.md` — revised through DeepSeek review 17 (clean branch falkordb-coolify-deploy); gate = golden fixtures in dev/oracle2/hosting/golden/; each review round is committed in this worktree branch by the coordinator after its edits.
- Gate: `python3 dev/oracle2/hosting/validate_falkordb_plan.py` + `services/oracle-brain/tests/test_falkordb_coolify_plan.py` pass.
- No live mutation.

## Next
Exact-head review on the clean branch; on APPROVE execute via the root coordinator's HOST-PATH (§6 0b). Open residuals: vm.overcommit_memory read, Trigger.dev public-route probe.

## Execution attempt 2026-10-14 (owner-approved deploy, plan @ (squashed into the clean-branch commit))
STOPPED at §6 preflight 0b before any change: no HOST-PATH from this session (ssh hetz / ai@ / root@100.66.37.58 → Permission denied (publickey); root@178.156.180.212:22 timed out). 0a/0c/name-collision preflights therefore not runnable. Nothing created on Coolify, Cloudflare or hetz; no secrets read. Resume: the root Oracle coordinator runs the plan from §6 step 0 over its own approved host path.

## Execution attempt 2 (2026-10-14, coordinator-supplied host path)
HOST-PATH substitution per coordinator/owner: `ssh -i ~/.ssh/916-alien -o IdentitiesOnly=yes ai@100.66.37.58` via one ControlMaster. Result: `connect to host 100.66.37.58 port 22: Connection refused`; port 22 stayed refused for a further 120 s (polled every 10 s); tailscale shows hetz active/direct. STOPPED again at §6 preflight 0b; 0a/0c/name checks not run. Nothing created; no secrets read. Resume once sshd accepts connections (likely rate limit / fail2ban), from §6 step 0.

## Execution attempt 3 (2026-10-14) — this session acted as HOST-PATH (root-coordinator role) via one ControlMaster `ai@100.66.37.58` (key 916-alien), per coordinator/owner
Preflight receipts (read-only): Coolify /version 4.4.6; /servers 200; tailscale hetz active/Online; 0c both 178.156.180.212 and 100.66.37.58 present; 0a overcommit_memory=0 (documented risk, Ansible item); collisions none (apps 12, services 2, databases 0, no oracle-falkordb*/oracle-graph-*, envs only production+synthetic-acceptance, no oracle-falkordb-* volumes/oracle-graph-* networks); ports 16390/16391 closed externally and unbound on host; no FalkorDB vault items exist yet.
STOPPED at 0b: hetz Docker Engine is 29.6.0, plan requires recording 29.1.3 (the version its network/forwarder proofs assume). Treated as preflight mismatch; nothing created. Resume needs coordinator decision: accept 29.6.0 (amend 0b) or re-prove §5 network behaviour on 29.6.0.

## Local re-proof on docker:29.6.0-dind (Compose 5.1.4; hetz Compose version not read), no hetz access
PASS: health; public 16390 + tailnet 6390 PONG; worker GRAPH.QUERY/RO_QUERY ok; worker CONFIG/MODULE/FLUSHALL/GET NOPERM, DEBUG unknown; default NOAUTH; no-cert/rogue-cert/plaintext refused; healthcheck PING only; graph net egress blocked (control bridge reached), masquerade=false; nginx re-resolve after recreate (172.19.0.3→.4) answered immediately, fwd not restarted; §8 backup rc 0; restore sha256 OK, aof=yes, canary=42.
DIFFERS: missing-tailnet-IP decoupling. With 100.66.37.58 absent (ip_nonlocal_bind=0), `compose up` rc=0, tailnet-fwd running and 100.66.37.58:6391 LISTENING via docker-proxy (no `cannot assign requested address`). Store + public 16391 fine. §6 0c text/decoupling claim is wrong for 29.6.0. 0b NOT amended; coordinator decision needed.
Follow-up (coordinator: amend): fresh dind, tailnet IP never assigned → compose rc 1, fwd Created, store healthy, public PONG; IP added later → tailnet still refused, fwd not auto-started (needs redeploy). Earlier "rc 0 + listening" came from a run where the IP had been present before removal. Plan 0b now requires 29.6.0 + Compose major ≥5 recorded; tailnet proven only by §9 check 4; receipts + overcommit=0 residual added.

## Execution attempt 4 (2026-10-15, after review 16 APPROVED; fixes committed (squashed into the clean-branch commit))
STOPPED before any host/SSH/Coolify/1Password/Cloudflare action: the plan's required gate `ai-task-gates check --before infrastructure` returned rc 3 — "STOP before infrastructure; declared: code; observed: deployment (protected)", escalated by branch files (.github/workflows/oracle-native-browser-image.yml, oracle-native-image.yml, oracle2-contracts.yml, task-gates.yml; apps/web|workers package.json; apps/workers/trigger.config.ts; dev/oracle2/{analytics,browser,hosting}/Dockerfile; packages/brain-contracts/package.json). The gate says a protected class cannot be reviewer-approved away; re-declaring with `ai-task-gates start --class deployment` (or running from a branch without those files) is a coordinator/owner decision, not taken here. No SSH connection opened; nothing created.

## Execution attempt 5 (2026-10-14, ~11:40 PM EDT; head 98d6bca, gate `check --before infrastructure` allowed)
Preflights passed: Engine 29.6.0, Compose 5.1.4 (recorded), both bind IPs present, tailnet active, Coolify 4.4.6, no name collisions, no pinned volumes/networks, 16390/16391 not answering (timed out, i.e. filtered — relevant to §9 check 4). `vm.overcommit_memory` = 0 (documented risk; separate Ansible item).
Created: vault items "Oracle FalkorDB — private CA", and per role "graph password", "server TLS", "worker client TLS" (certs notAfter 2027-01-13); Coolify environment `oracle-graph-production`; Coolify service `oracle-falkordb-confirmed` (instant_deploy false, never started, all containers exited/not created; UUID in issue receipt only).
STOPPED at §6 step 3 (confirmed): `POST /services/<SVC>/envs` → 409 "Environment variable already exists. Use PATCH request to update it." Coolify 4.4.6 auto-created both env keys, EMPTY, from the compose `${VAR}` references. Per the plan's 4xx rule nothing else was done: no envs set, not started, candidate service not created, no DNS record, no backup task. §9 checks not run. Plan amendment needed: step 3 must PATCH the auto-created keys (fail-closed: container refuses to start with empty values).

## Execution attempt 6 (2026-10-14, ~11:50 PM EDT; head 8f36f5d, gate allowed with final-check 20)
Resumed with attempt-5 objects (no duplicates). confirmed: step 3 PATCH FALKORDB_PASSWORD 201, PATCH FALKORDB_SERVER_TLS_B64 201; step 4 read 200, no FQDN, both keys present and set. STOPPED at §6 step 5: `GET /services/<SVC>/start` → 405 "This endpoint has changed to a POST request." Per the 4xx rule nothing further: confirmed configured but NOT started; candidate service not created; no DNS, no backup task; §9 not run. Plan amendment needed: step 5 (and likely step 8 restart/stop verbs) use POST on this Coolify build.

## Execution attempt 7 (2026-10-15 ~12:00 AM EDT; head fe587ca, gate allowed with final-check 21)
confirmed: envs re-PATCHed 201, `POST /start` 200. candidate: service created 201, envs PATCH 201 (auto-created keys), read 200 no FQDN, `POST /start` 200. On hetz both stores are running+healthy, published 178.156.180.212:16390/16391 and 100.66.37.58:6390/6391; data-files exited (expected).
STOPPED at the §5 network rule: Coolify attached each falkordb and tailnet-fwd container to an extra per-service network named after the service UUID (bridge, internal=false, default masquerade → egress-capable) besides `oracle-graph-<ROLE>`. Plan: "if it does, STOP and report (do not accept an egress-capable network)". Nothing further done: no DNS record, no backup task, §9 checks not run. LEFT IN PLACE AND RUNNING: both Coolify services (stores up, listening publicly with mTLS+ACL, empty data). Decision needed: stop the services now, or amend the plan (e.g. compose `networks` override / Coolify setting that suppresses the default network) and re-review.

## Execution attempt 8 (2026-10-15 ~12:10 AM EDT; head 970d41b, gate allowed with final-check 23)
STOPPED at §6 step 4a's first check, before any mutation: `docker network inspect <SVC>` lists, besides this role's falkordb and tailnet-fwd, `coolify-proxy` (Traefik) on BOTH per-service networks (h8yu… confirmed, tsxh… candidate). Rule: "list only this role's containers (else STOP)". Nothing stopped, disconnected or recreated. Both services remain RUNNING as after attempt 7. Plan needs to say how to handle coolify-proxy (Coolify connects it to every service network; it also gives the proxy a path into the store network).
