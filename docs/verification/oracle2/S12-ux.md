# S12 product experience — offline evidence

Status: offline building-block leaf landed (synthetic/invented only).
Recorded: 2026-10-20 (S08/S12 offline leaf landing).

## Offline tests

test_s12_completeness_gate.py (7 passed, 0 skipped)

## Landed modules

- services/oracle-brain/oracle_brain/knowledge/product_experience_gate_v1.py

Named gate rewritten with real assertions (was a pure skip stub). Import guard
replaced by live imports; tests assert the gate refuses completeness when
upstream stages are missing or incomplete (REQUIRED_UPSTREAM_STAGES S03–S11).

verify_phase.py S12 --mode offline: 7 passed (FIXTURE_ONLY).

## Notes

Ported from origin/claude/s12-product-experience. Playwright workspace.spec.ts,
accessibility.spec.ts, exports.spec.ts still skip with the named page blockers
(consultant UI pages unbuilt). Visual review and task-success rubric remain open.

## Live acceptance

Not accepted / business and live acceptance stay closed.
This does not close #36. No employees, no company data, no production actions.


## Independently installed employee recipient selection — source preparation

The protected web adapter can consume one independently installed finite recipient
index (at most 64 employee/auth recipients, closed eight-purpose bindings, actual
protected-file size limit 65,536 bytes). The index supplies only exact existing
profile path/hash pins for control, original viewing, upload, review, conversation,
meeting control, web answer and employee MCP. It is not an appointment, source-read
permission, group role, company policy or technical issuer. Each selected existing
profile and its backend peer/SQL purpose must still be independently installed.
No runtime constructor creates profiles, keys, roles, grants or resources.

Selection follows actual server `getUser` and exactly one current SQL employee
identity row. A duplicate identity, disabled employee, wrong configured/actual auth
project, unmatched auth user/employee, or missing purpose refuses. Request bodies,
unverified cookies, actor headers, URLs and browser storage cannot select an
arbitrary recipient/profile. Session cookies still require actual server auth.
Each protected operation captures its original wall/monotonic window before auth,
index, profile or body work; actual identity is verified again around transport.
The existing same-origin, strict payload, source scope and response guards remain.

The one index is canonical closed JSON, pinned to actual private file/device/inode/
owner/mode/ancestor identity, distinct issuer/reviewer, and a finite original
horizon. Profiles retain their own exact recipient/TLS/peer/currentness checks,
private credentials and source rights. Caches are bounded and keyed by actual
recipient plus fixed purpose, never by a global last employee. Cross-profile
certificate/URI/public-key reuse refuses. Re-reading the same selection verifies
the same current index and private profile; file replacement (even same bytes),
changed configured pins, expiry or a missing entry cannot cause a fallback.
A partially configured index refuses. With no index configured, the retained
single-recipient APIs and existing application identity behavior remain available.

The actual loopback proof uses two distinct mTLS credentials and the production
web adapter, with explicitly invented auth-import snapshots. It checks A/B/A
profile isolation, wrong/disabled/ambiguous recipient refusal, payload actor
refusal, backend denial for another recipient's requested run, and same-byte index
replacement refusal. These are not real Auth/employee SQL, installed enterprise
multi-user, browser, company or business proof. The new SQL identity lookup and
complete actual two-user browser-to-backend/store behavior still require their
separate integrated proof. No acceptance checkbox is closed by this source work.

The whole S12 requirement remains open: meaningful home/process/correction/inbox/
health/export experience, English/Simplified Chinese and keyboard/mobile behavior,
loading/empty/partial/stale/error/no-access states, full current permissions and
actual two-role task success. Protected source, answer, interview, research and
recommendation components must be integrated without promoting old pilot or
invented fixtures into employee/company acceptance. Business acceptance remains
separately held by Albert under parent #24.
