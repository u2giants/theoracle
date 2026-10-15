---
issue: 27
status: OPEN
owner: claude/falkordb-coolify-deploy (Claude chat 3eb42441-e756-4adf-9c4c-d00bde904327, edge-dev3)
---

# FalkorDB on Coolify — deployed; two S03 leftovers remain

## 0. ⚠️ BUSINESS DECISIONS ONLY THE OWNER CAN MAKE
- **When staff review happens (decided October 15, 2026).** Staff review stays in the plan, but it comes LAST. Ilona, Jessica and other staff get nothing to review, check, grade or try until all of S03–S16 is built and proven with invented or automated checks. See the comments on [#24](https://github.com/u2giants/theoracle/issues/24#issuecomment-6196751788) and [#27](https://github.com/u2giants/theoracle/issues/27#issuecomment-6196752119). [#58](https://github.com/u2giants/theoracle/issues/58) is open and titled "DEFERRED". The plan document itself has not been edited to say this yet.
- **Paused work.** Company questions, reports, employee messages and grading on #27 stay PAUSED. The approval to run them expired on October 13. Only Albert can renew it.
- **Off-server backup destination.** Albert decides where the off-server backup copy goes and whose account pays for it.

## 1. What this application is
The Oracle ([u2giants/theoracle](https://github.com/u2giants/theoracle)) is being rebuilt as an evidence-backed consultant for the company. Parent issue: [#24](https://github.com/u2giants/theoracle/issues/24), with stage children S01–S16 (#25–#40). S01 and S02 are closed. S03 ([#27](https://github.com/u2giants/theoracle/issues/27)) is open.

## 2. What we set out to do this session, and why
Deploy the two graph databases on Coolify at hetz: FalkorDB "confirmed" holds what has been confirmed, and FalkorDB "candidate" holds candidate knowledge. This is part of S03's live proof. The plan is [docs/implementation/falkordb-coolify-deploy-plan.md](https://github.com/u2giants/theoracle/blob/main/docs/implementation/falkordb-coolify-deploy-plan.md).

## 3. Current state — what is true right now
- Both databases are running on Coolify at hetz.
- The public route is 178.156.180.212, port 16390 (confirmed) and port 16391 (candidate), at oracle-graph.designflow.app. Clients must present a TLS client certificate.
- All nine §9 checks PASS: security, passwords, internet access cut off, surviving a restart, nightly backups, a test restore, and the public route. The check-4 receipt is commit f9edc63.
- Merged as [PR #126](https://github.com/u2giants/theoracle/pull/126), merge commit 7e84dba.
- Nightly backups run on the server itself only.

## 4. Everything we tried that did NOT work
- **Check 4 (public route) kept timing out.** A tcpdump on hetz captured 0 packets, and the nft DNAT rule counter stayed at 0. That proved Hetzner's cloud firewall was blocking the traffic, not the server. Albert opened 16390/16391 by hand, and the check then passed.
- **The CI job oracle2-offline failed** with "all predefined address pools have been fully subnetted" on edge-dev3. Old, empty Docker networks from earlier test runs had used up the address space. I removed 26 empty oracle-* networks, and the rerun passed.

## 5. Root causes and key findings
- New public ports on hetz also need a rule in the Hetzner Cloud firewall. No Hetzner API token is saved in 1Password.
- Test runs on edge-dev3 leak Docker networks. If CI fails with the address-pool error again, remove the empty `oracle-synthetic-*` / `oracle2-ci-*` networks.

## 6. Exact next steps
1. Add the "remove on rollback" item for the oracle-graph.designflow.app DNS record to #27's rollback list.
2. Set up the off-server backup copy for both FalkorDB roles: a nightly upload to storage off hetz. Then prove a restore from that copy and record the receipt on #27. Ask Albert for the destination first (see §0).
3. Continue S03's remaining live proof, starting from #27's latest comments.

## 7. Constraints and gotchas in force
- No staff review before S03–S16 is complete (see §0).
- Pushes to main go through a PR, and CI must pass before merging.

## 8. Access and environment
- hetz runs Coolify.
- edge-dev3 is the CI runner and the test client. Its client certificate is used for check 4.
- Credentials are in the 1Password vault `vibe_coding`.

## 9. Open questions and risks
- Until the off-server copy exists, losing hetz means losing the FalkorDB data.
- The old plan-drafts branch `claude/falkordb-coolify-plan` was never merged. Main has replaced its content (via #126), and it is kept only for history.
