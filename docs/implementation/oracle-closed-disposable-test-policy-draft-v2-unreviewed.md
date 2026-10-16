# Closed disposable-test policy — design draft v2

**STATUS: UNREVIEWED DRAFT — NOT AUTHORITY.**
**This document is not approved and grants no execution, database, deployment, browser, or policy-code permission.**
**It is a substantive prospective design for a future assigned review only. Do not implement any part of it before that review explicitly APPROVEs a later revision.**

- Date: October 16, 2026
- Scope: a future closed disposable-test capability for isolated Oracle replacement work
- Parent: u2giants/theoracle#24 (replacement), successor step 7 companion
- Supersedes in design intent only: proposal `740f9f45933801b1a1bc67ba3d9d2a72e27c137af4dafa39582d7019a0510bc7`
- Prior review outcome: DeepSeek PLAN review 3141 **TERMINAL REJECT** (report SHA256 `9e8606b48977881dcb84aac17add37007418dcdfd57fc3f1d6d32b45d1749830`). This draft is **not** a patch presented as approval, and **not** a retry of 740f9. It is a new design that must survive a new assigned review before any policy code exists.

---

## 1. Why this draft exists

The closed disposable-test policy proposal 740f9 was terminal-rejected. The recorded findings are binding design inputs:

| Severity | Finding (DeepSeek 3141) | Design response in this draft |
|---|---|---|
| High | Unsealed verified-bytes execution TOCTOU | §3 sealed-bytes bind: verification and execution are one exclusive operation over the same inode/bytes |
| High | External-network assertion without enforcement | §4 enforced network isolation as a precondition of the executor, not a claim |
| High | Execution inside a data-only gate | §5 hard separation: data-only gates never execute; execution gates never read untrusted data as code |
| Medium | Guardian O_EXCL consume/receipt | §6 real guardian with `O_EXCL` create, single consume, durable receipt |
| Medium | Stronger path/class registration | §7 allowlisted absolute paths and declared task classes, registered before any action |
| Medium | SQL-vs-Docker fresh-write proof | §8 independent fresh-write proof across both SQL and Docker targets |

Nothing in this document is acceptance, live proof, or permission. The U1–U6 browser/source ledger remains open. No policy code follows from this draft.

---

## 2. Non-goals

- No production, deployment, hosted, shared-db, or application database action.
- No real provider, credential, paid dispatch, or external API call.
- No browser deployment-class database action (the recorded refusal stands; there is no acknowledgement or class-dropping workaround).
- No replacement of `ai-task-gates`, reviewer rotation, claim-first shared-db rules, or release policy.

---

## 3. High — sealed verified-bytes execution (TOCTOU closure)

**Problem.** 740f9 verified bytes and then executed them after a gap in which the object could change.

**Design.**

1. The execution subject is one immutable regular file, opened once with `O_RDONLY|O_NOFOLLOW` (or platform equivalent that refuses symlink/follow races).
2. Verification and execution share one open file description:
   - hash the open handle (`sha256` over the handle bytes);
   - compare to the registered expected digest;
   - execute only that same handle (e.g. `fexecve` / sealed FD handoff), never a path re-open.
3. Any mismatch between the pre-exec hash and the registered digest refuses before any instruction runs.
4. After execution the same handle is re-hashed; a changed object is a recorded incident and the attempt is terminal-failed, never retried.
5. The registry binds: absolute path, device+inode, size, mtime_ns, mode, sha256, declaring task class. A changed inode invalidates the registration; there is no in-place update.

**Invariant.** Verification and execution are one exclusive operation over the same bytes. There is no verify-then-open gap.

---

## 4. High — external network isolation is enforced, not asserted

**Problem.** 740f9 asserted "no external network" without a mechanism.

**Design.**

1. The disposable executor runs only inside a pre-created network namespace with **no external route** (loopback only), or inside a container with an explicit empty network (`--network none`), chosen at registration.
2. Capability to run is granted only after an independent probe inside that namespace fails to reach any non-loopback destination; the probe result is part of the receipt.
3. DNS, proxy, and IPv6 routes are included in the refusal set. A reachable default route is a hard fail closed before data is read.
4. "We did not observe egress" is not evidence. The only accepted evidence is the namespace/network topology plus the negative probe, both sealed into the receipt.

---

## 5. High — data-only gates never execute; execution gates never interpret data as code

**Problem.** 740f9 allowed execution inside a gate whose authority was data-only.

**Design.**

1. Two disjoint registries:
   - **Data-only registry** — files and commands that may only be read, hashed, compared, diffed, or stored. The runner for this registry has no execute bit on any subject and uses a read-only mount.
   - **Execution registry** — sealed executables admitted under §3, run only under §4 isolation.
2. A data-only gate result can *authorize a later execution-gate entry* in the same session, but the data-only runner physically cannot execute. Conversely, an execution runner refuses any subject whose class is data-only.
3. Task class names are disjoint (`*-data` vs `*-exec`). Crossing the boundary is a registration error, not a warning.

---

## 6. Medium — guardian `O_EXCL` consume and receipt

1. Before any disposable action, a guardian creates the attempt receipt file with `O_CREAT|O_EXCL|O_WRONLY`, mode `0600`, at a registered path. Failure to create means the attempt id was already consumed; there is no overwrite path.
2. Exactly one consume per receipt. The guardian records: attempt id, declaring class, subject digest, network topology id, start time, end time, exit status, post-exec hash.
3. Receipts are append-only; deletion is not an operation. A second consume of the same attempt id is refused by the filesystem, not by a best-effort check.
4. The guardian is the only writer of receipts. Test code cannot forge, replace, or clear one.

---

## 7. Medium — stronger path and class registration

1. Every subject path is absolute, canonical, symlink-free at registration, and inside an allowlisted root for its class.
2. Registration includes: path, digest, inode identity, task class, declaring session, and expiry. Expired registrations refuse rather than warn.
3. Class changes require a new registration; there is no in-place class edit.
4. Unknown paths, unregistered classes, path escapes (`..`, symlink swap, mount escape), and world-writable subjects refuse closed.

---

## 8. Medium — SQL-vs-Docker fresh-write proof

1. A disposable test that writes must prove freshness **per target**: each target (SQL fixture and Docker file-system) starts from a recorded empty/fresh state, and the proof is the target's own observation, not a cross-inference.
2. SQL proof: a fresh fixture identifier, a write that fails if the key pre-exists (unique constraint / advisory lock), and a read-back of the exact written row.
3. Docker proof: `O_EXCL` create inside a fresh container/volume, with post-write stat and hash of the written object.
4. "SQL shows a row" is never proof of a Docker write, and vice versa. Both proofs are required when both targets are in scope; a missing proof abstains as UNKNOWN, never success.
5. Freshness proofs are part of the §6 receipt. No cleanup claim follows from an unproven write.

---

## 9. Lifecycle honesty (aligns with U6)

The policy runner's public states remain the truthful U6 set:
`pending / processing / awaiting-external-phase-or-custody / missing-evidence / revision_pending / cancel-requested / cancelled / failed / UNKNOWN`.

- Cancel intent is never stop proof.
- No automatic paid retry/rePOST/new budget/horizon/epoch/reset.
- A spent dispatch is never disguised as retry.
- Recovery consumes an independently appointed existing attempt without another POST.
- Missing evidence abstains; no stale answer, map, or badge survives invalidation.

---

## 10. Review and activation path (future work — not this session)

1. A new assigned reviewer (rotation-compliant, engine-different) reviews **this design** as a plan.
2. Only after an explicit APPROVE of a revision of this document may policy code be written.
3. Policy code itself needs its own implementation review before any blocked database or deployment-class action.
4. Until both reviews exist, the recorded browser deployment-class database refusal stands and is preserved.

---

## 11. Explicit non-claims

- This draft is **unreviewed** and is **not authority**.
- It is **not** DeepSeek-approved and must not be cited as such.
- It does not accept, prove, or unlock U1–U6, live proof, business acceptance, or any database action.
- No implementation, test execution against real targets, or enforcement code accompanies this draft.
