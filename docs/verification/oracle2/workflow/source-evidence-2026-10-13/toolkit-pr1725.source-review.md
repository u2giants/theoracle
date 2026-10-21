> Link-corrected rendering only. The [byte-identical original report](https://github.com/u2giants/theoracle/blob/c3076ee821a4e5efa708149ce5fc91cb400e5c4e/docs/verification/oracle2/workflow/source-evidence-2026-10-13/toolkit-pr1725.source-review.md) is preserved at Git blob `f522138ce16b0a843761e2c1269c66a39555ae09`, SHA256 `a126775f41953d32f3af06f3d61a97cc3e41ef91626173fe4671fe0a19ed2f8a`. Review verdict, reviewed source, findings and historical authority are unchanged; this rendering is not a new approval.

# muse security-review — 20261013T232152-1535950-28734

| field | value |
|---|---|
| provider | `muse` |
| repository | `/home/ahazan/.codex/worktrees/oracle-native-toolkit-v2-reviewed` |
| reviewed commit | `6162c407d870ebaf16675a1be6a05d05e911c743` |
| source digest | `69150a9feecf4999489d3414197318085fc5588eb7dc2e39a763a02493c6e654` |
| run | `20261013T232152-1535950-28734` |
| caller | `zcode` |
| elapsed seconds | `295` |
| runner | `ai-review-engine` (review-lifecycle-core/1) |
| tools | door muse |
| packet | `cee7bcf765ed84f23950c8bee643684de18a6beeee3f817578ea35dcf97d13a0` |

## Result

# Muse review — runner door

| field | value |
|---|---|
| model | `muse-spark-1.3-contributor` |
| engine | `muse-code` |
| reviewed commit | `6162c407d870ebaf16675a1be6a05d05e911c743` |

---

### Findings and reasoning

**Provisional verdict: APPROVE** (pending final write-up; continued investigating and found no blocking issue).

Reviewed head: `6162c407d870ebaf16675a1be6a05d05e911c743` (verified: `git rev-parse HEAD` matches; working tree clean). This change adds a closed Oracle offline-serialization action (v1/v2 profiles, guardians, runtimes, control/output helpers), wires it through `ai-review` / `ai-review-sandbox` / `ai-task-gates` / code-only export, and adds docs, fixtures, and tests.

# Findings

## High

None.

## Medium

None.

## Low / informational

1. **Guardian `main()` omits `RecursionError` from its fail-closed catch (noisy but still closed).** A deeply nested stdin manifest raises `RecursionError` from `json.loads`, which escapes the `(OSError, ValueError, KeyError, TypeError, SubprocessError)` handler and exits via traceback instead of the clean refusal message. No action is taken (exception precedes any claim), but it is inconsistent with the profile entry points, which do catch it.
   - [guardian.py](https://github.com/popcre/ai-devops/blob/6162c407d870ebaf16675a1be6a05d05e911c743/tools/oracle_native_alternate_guardian.py#L182) and [v2 guardian](https://github.com/popcre/ai-devops/blob/6162c407d870ebaf16675a1be6a05d05e911c743/tools/oracle_native_alternate_v2_guardian.py#L184); contrast [profile](https://github.com/popcre/ai-devops/blob/6162c407d870ebaf16675a1be6a05d05e911c743/tools/oracle_native_alternate_profile.py#L281).

2. **Reviewer-prompt interpolation does not hex-validate descriptor SHAs.** `bin/ai-review` appends `prompt()` output (which embeds `permission_registration_descriptor_sha256` / `manifest_descriptor_sha256` from lifecycle state) into the reviewer prompt without format checks. Lifecycle state is owner-only 0600 under a validated control path, and `completed()` independently re-checks dual exact scopes and report hash, so a tampered value breaks approval rather than forging it — hardening-only.
   - [ai-review](https://github.com/popcre/ai-devops/blob/6162c407d870ebaf16675a1be6a05d05e911c743/bin/ai-review#L98), [prompt()](https://github.com/popcre/ai-devops/blob/6162c407d870ebaf16675a1be6a05d05e911c743/tools/oracle_native_alternate_profile.py#L253).

3. **Legacy-router assumes `sys.argv[2]` is the state path.** The new routing block in `review_action_profile.py main()` inspects `sys.argv[2]` positionally; a flag-first legacy invocation (e.g. `--manifest m capture state`) in Oracle context is refused instead of parsed. Fail-closed, availability-only; all in-repo callers pass positionals first.
   - [review_action_profile.py](https://github.com/popcre/ai-devops/blob/6162c407d870ebaf16675a1be6a05d05e911c743/tools/review_action_profile.py#L364).

4. **v1 omits `source_head`/`source_digest` format checks that v2 has.** v1 `validate_manifest` does not assert 40/64-hex shape, but `binding()` equality-binds both to validated lifecycle state, so no bypass — consistency nit.
   - [v1 profile](https://github.com/popcre/ai-devops/blob/6162c407d870ebaf16675a1be6a05d05e911c743/tools/oracle_native_alternate_profile.py#L112) vs [v2 profile](https://github.com/popcre/ai-devops/blob/6162c407d870ebaf16675a1be6a05d05e911c743/tools/oracle_native_alternate_v2_profile.py#L115).

5. **Committed fixture discloses a developer-machine absolute path.** `tests/fixtures/oracle-native-public-producer.md` embeds `/home/ahazan/.codex/worktrees/...`. Trivial local-layout disclosure, no credentials (secret-pattern grep over all changed production, test, doc, and fixture files is clean).
   - `tests/fixtures/oracle-native-public-producer.md:900` (original unverified line locator; the [pinned source file](https://github.com/popcre/ai-devops/blob/6162c407d870ebaf16675a1be6a05d05e911c743/tests/fixtures/oracle-native-public-producer.md) contains 388 lines).

## Verification notes (what I checked, not findings)

- **Authorization:** dual exact scoped lines + genuine native completion + 300 s window + `VERIFIED_INSTALLED_SOURCE` + one-use `O_EXCL` spent marker *before* any content-capable open; test mode can never consume authority ([guardian consume](https://github.com/popcre/ai-devops/blob/6162c407d870ebaf16675a1be6a05d05e911c743/tools/oracle_native_alternate_guardian.py#L27), [completed()](https://github.com/popcre/ai-devops/blob/6162c407d870ebaf16675a1be6a05d05e911c743/tools/oracle_native_alternate_profile.py#L196)). Distinct v1/v2 admission keys and spent prefixes. Task-gate branch pins Oracle/private-tooling/exact opt-in gate.
- **File boundaries/permissions:** O_PATH + nofollow traversal, 0600 single-link files / 0700 dirs, full stat-identity (incl. ctime) revalidation around opens, fd-anchored runtime/output verification, sealed memfds, fixed `/usr/bin/bwrap|/usr/bin/ldd|/usr/bin/git|/usr/bin/python3`. Code-only `.md` exception is pinned to an exact blob at HEAD/worktree/base/current bytes plus exact remote + path-closure checks; denied/licensed/suffix checks still apply otherwise.
- **Injection/secrets:** all subprocess calls use argv lists with fixed binaries, no `shell=True`/`eval`; sealed git env drops `GIT_*`/secret forwarding; `AI_TASK_GATES_DIR` passthrough matches pre-existing legacy convention exactly; evidence projections are allowlisted (no paths/private values). New `.cmd` launchers are byte-identical to the existing repo template.
- **Tests:** all new Python files compile; shell files pass `bash -n`. Ran `test-oracle-native-alternate-control.py` (13/15 pass) and `-security.py` (6/7 pass); the 3 failures are environmental — this sandbox UID-shifts `/usr` (uid 65534, not 0), tripping the root-owned-OS prechecks — and every one fails in the *closed* direction (refusal before any read/claim), confirming fail-closed behavior. The producer fixture sha256 matches the pinned `e933892b…` blob.


---

## Verdict
APPROVE
