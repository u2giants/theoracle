# muse security-review — 20261014T000558-1619012-22869

| field | value |
|---|---|
| provider | `muse` |
| repository | `/tmp/oracle-coordinator-lec5sbj8/platform-v5-final-check-ilm8s95s` |
| reviewed commit | `274f9ac16f73f78e7a222969f418d5c38e418c4c` |
| source digest | `6782a9aade959286cfb3b368876f6710d2f84469c2a056b84e56526df4a3b825` |
| run | `20261014T000558-1619012-22869` |
| caller | `zcode` |
| elapsed seconds | `178` |
| runner | `ai-review-engine` (review-lifecycle-core/1) |
| tools | door muse |
| packet | `08ab9aed259185a9849465a5be7fc5523049ab70a1e462dd7ac9d593a02ede6d` |

## Result

# Muse review — runner door

| field | value |
|---|---|
| model | `muse-spark-1.3-contributor` |
| engine | `muse-code` |
| reviewed commit | `274f9ac16f73f78e7a222969f418d5c38e418c4c` |

---

### Findings and reasoning

Provisional verdict: APPROVE — no material security risk seen in full patch pass.

Reviewed head: `274f9ac16f73f78e7a222969f418d5c38e418c4c`

Scope: authorization, data leakage, injection, secrets, file boundaries, permissions only. Ran read-only checks over `tools/oracle-platform-capability/`; no hardcoded secrets, no `shell=True`/`os.system`, subprocess calls use fixed argv without shell.

## Findings

### High — None

### Medium — None

### Low / Informational — None

Verification notes (not findings, with evidence):

- Credentials stripped from environment at import before any project import, never in child env/argv/logs: [inspect_capability.py](/home/ahazan/.local/state/ai-devops/review-sandboxes/rlc-muse-837e705c381e-01eca101dbd9/tools/oracle-platform-capability/inspect_capability.py:16), child envs fixed at lines 119, 192, 425.
- SSH password held 0600 under 0700 custody, askpass validates inode/size/mode/UID via anchored proc-FD, output via anonymous files: [inspect_capability.py](/home/ahazan/.local/state/ai-devops/review-sandboxes/rlc-muse-837e705c381e-01eca101dbd9/tools/oracle-platform-capability/inspect_capability.py:105).
- API token shape `getgen!` excludes space/control/NUL, checked before tailnet/claim/network; Bearer [REDACTED] in-memory header only, no proxy/redirect, interface+source pinned with no fallback: [inspect_capability.py](/home/ahazan/.local/state/ai-devops/review-sandboxes/rlc-muse-837e705c381e-01eca101dbd9/tools/oracle-platform-capability/inspect_capability.py:248).
- Remote command is base64-only inside single quotes (alphabet has no quote/breakout chars); SSH target is `ai@host` with host regex, passed as one argv element, no shell: [inspect_capability.py](/home/ahazan/.local/state/ai-devops/review-sandboxes/rlc-muse-837e705c381e-01eca101dbd9/tools/oracle-platform-capability/inspect_capability.py:94).
- Fixed IPv4 version URL, canonical form, userinfo/query/fragment denied: [inspect_capability.py](/home/ahazan/.local/state/ai-devops/review-sandboxes/rlc-muse-837e705c381e-01eca101dbd9/tools/oracle-platform-capability/inspect_capability.py:173).
- File custody: nofollow/nonblock, regular single-link, 0700 dirs / 0600 leaves / O_EXCL, held-FD rechecks, FIFO/device refused: [inspect_capability.py](/home/ahazan/.local/state/ai-devops/review-sandboxes/rlc-muse-837e705c381e-01eca101dbd9/tools/oracle-platform-capability/inspect_capability.py:26).
- Private inputs held outside ordinary/linked/bare Git, exact 0600/142-byte known-hosts, rechecked through gate/claim/transport: [inspect_capability.py](/home/ahazan/.local/state/ai-devops/review-sandboxes/rlc-muse-837e705c381e-01eca101dbd9/tools/oracle-platform-capability/inspect_capability.py:396).
- Gate + one-use O_EXCL claim ordering with lifetime/tailnet/installed-gate checks before and after gate; failure stays spent, no retry: [inspect_capability.py](/home/ahazan/.local/state/ai-devops/review-sandboxes/rlc-muse-837e705c381e-01eca101dbd9/tools/oracle-platform-capability/inspect_capability.py:418).
- Projection emits only schema/hashes/commitments/counts, no target/peer/credential/path values; errors generic without echo: [describe_action.py](/home/ahazan/.local/state/ai-devops/review-sandboxes/rlc-muse-837e705c381e-01eca101dbd9/tools/oracle-platform-capability/describe_action.py:32).
- Remote program fixed argv only, bounded outputs, expiry enforced locally and remotely, zero mutations: [remote.py](/home/ahazan/.local/state/ai-devops/review-sandboxes/rlc-muse-837e705c381e-01eca101dbd9/tools/oracle-platform-capability/remote.py:6).


---

## Verdict
APPROVE
