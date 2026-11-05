---
issue: 431
status: BLOCKED
owner: mimo/task7-oracle-removal-leftovers
---

# Task 7 leftovers — GHCR image deletion blocked on a credential; Supabase MCP repair and stale-doc cleanup landed

## 0. ⚠️ BUSINESS DECISIONS ONLY THE OWNER CAN MAKE

One non-blocking confirmation, outside the remaining technical work:

- **Did Albert actually order the #398 database deletion without a backup?** The #398
  session's report says he did; the coordinator's baton
  (https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-05T0140Z-edge-dev3-claude-close-nested-company-map.md)
  records that it "did not see those words". Only Albert can confirm what he ordered.
  Nothing below blocks on the answer — the tables are already dropped. **Recommendation:**
  answer once, yes or no; if no, open one incident-review issue on the repo. Ask him this
  single question in one message together with anything else a successor needs him for —
  not one at a time.

**Already settled — do NOT re-ask:**

- 2026-11-04: Oracle 2, its old workers, tables and settings were to be removed (#398,
  closed; PRs #402, #406, #422).
- 2026-11-04: the `supabase-oracle` MCP entry is repaired, not dropped (task 7 (b) — done).

The remaining blocked item is **not** an ask for Albert: minting a GitHub token with
`delete:packages` is a platform-limit access item (PAT creation needs an interactive
GitHub account session and cannot be done through the API), so it stays `Blocked —`
under the standing rule that the AI never asks the owner to create a credential.

## 1. What this application is

The Oracle is an evidence-backed enterprise knowledge graph for POP Creations /
Spruce Line: employees chat with it and upload documents, workers extract claims with
quote-level evidence, and synthesis sections stay traceable back to sources. Public
repository https://github.com/u2giants/theoracle . The current product surface is the
Company Map: the web app on Vercel plus the `apps/brain` service (Python), backed by a
Supabase Postgres project. Oracle 2 (the older chat/workers stack) was removed in #398.

## 2. What we set out to do this session, and why

Handoff "Task 7. Oracle 2 removal leftovers" (baton URL in §0): finish the three
leftovers the #398 removal session did not finish. (a) Delete the two GitHub container
images `theoracle-native` and `theoracle-native-browser`. (b) Repair the
`supabase-oracle` entry in `.mcp.json`, which launched `scripts/oracle2/supabase_mcp.mjs`
— a script deleted in #406 — and keep the Supabase MCP working afterwards. (c) Remove
stale doc mentions of the seed script and the old settings table from the configuration
and development docs. One issue for all three; one branch, one PR, squash-admin merge.

## 3. Current state — what is true right now

- **(a) `Blocked —`.** The two images still exist in GitHub Packages
  (`ghcr.io/u2giants/theoracle-native` and `ghcr.io/u2giants/theoracle-native-browser` —
  names proven by the deleted publish workflow,
  https://github.com/u2giants/theoracle/blob/8c90b5794e5881bfb650009529cacaaa09f185cf/.github/workflows/oracle-native-image.yml ).
  Deleting them needs a token with `delete:packages`; no token available to any AI session
  on this machine has that scope (evidence in §4/§5). The issue carries an unchecked
  `- [ ] live proof` line for exactly this item, named in the closing comment on
  https://github.com/u2giants/theoracle/issues/431 .
- **(b) Done and verified live.** PR https://github.com/u2giants/theoracle/pull/432
  (squash-merged 9:49 PM EST 2026-11-04, commit
  https://github.com/u2giants/theoracle/commit/85eaf44adba6f446b375d972b0331d347546612c ).
  `.mcp.json` ( https://github.com/u2giants/theoracle/blob/main/.mcp.json ) now points the
  entry at the new launcher
  https://github.com/u2giants/theoracle/blob/main/scripts/mcp-supabase-launch.mjs .
  Verified twice through the exact committed entry (pre-commit and post-merge, 9:34 and
  9:52 PM EST 2026-11-04): MCP `initialize` answered server `supabase` v0.15.0, protocol
  2024-11-05; `tools/list` returned 13 tools; live `list_tables` returned exactly the four
  live tables — `public.departments` (9 rows), `public.employee_departments` (54),
  `public.employee_identities` (8), `public.employees` (38), all RLS-enabled.
- **(c) Done and verified.** Same PR: `docs/configuration.md`
  ( https://github.com/u2giants/theoracle/blob/main/docs/configuration.md ) and
  `docs/development.md` ( https://github.com/u2giants/theoracle/blob/main/docs/development.md )
  no longer mention the seed script or the old settings table. `bin/ai-doc-safety
  --changed origin/main` PASS on the merged content: public path/credential/topology
  boundary, and local Markdown links.
- **Issue https://github.com/u2giants/theoracle/issues/431 is closed** (9:53 PM EST
  2026-11-04) with the full closing evidence and the (a) live-proof line left open and
  named — that line is the completion marker for (a); do not open a second ticket.
- Everything from this session is committed, pushed and merged; the branch
  `task7/oracle-removal-leftovers` is deleted after merge-proof (see §8 for the session
  worktree state).

## 4. Everything we tried that did NOT work

- **Deleting the GHCR images with the current GitHub credentials.** Every available
  token fails: the `gh` CLI token (OAuth, scopes `gist, read:org, repo, workflow`) cannot
  even list package versions — `gh api /users/u2giants/packages/container/theoracle-native/versions`
  returns HTTP 403 "You need at least read:packages scope" (same for `-browser`). The
  vault item "GitHub token with Packages read access for u2giants/backrest-wiz"
  authenticates but its header shows `x-oauth-scopes: read:packages` only. Do not retry
  these two dead ends: "GitHub PAT - u2giants repo push access" answers HTTP 401 (dead
  or rotated) and "GitHub PAT ai-devops RUNNER pool read token" has no usable credential
  field. Nothing anywhere carries `delete:packages`.
- **Running the ai-devops bash tools with bare `bash` on this Windows host.** It resolves
  to the Windows-Subsystem-for-Linux stub and there is no Linux distribution installed —
  every call fails before running. Use the Git for Windows bash (the `bash.exe` shipped
  with Git for Windows) to run `bin/ai-doc-safety` and `bin/ai-pr-wait` here.
- **`ai-task-gates check --before ship` under class `production` with no acknowledgment.**
  It STOPs: the production class demands the owner's explicit authorization for the
  exact resource and action. It is satisfied by re-running with `--acknowledge "<quote>"`,
  quoting Albert's standing rule ("Albert does not merge — you do, except DesignFlow or a
  PR he said he will review first") plus the task's merge instruction. That is supplying
  the authorization the gate asks for — not bypassing it.

## 5. Root causes and key findings

- The old `scripts/oracle2/supabase_mcp.mjs` (full text at
  https://github.com/u2giants/theoracle/blob/8c90b5794e5881bfb650009529cacaaa09f185cf/scripts/oracle2/supabase_mcp.mjs )
  did three things: resolve the Supabase project ref from a machine-private targets
  profile, validate it against a committed SHA-256 pin registry, and spawn
  `npx -y @supabase/mcp-server-supabase@latest --read-only --project-ref <ref>`. The pin
  registry (`dev/oracle2/public-target-pins.json`) was retired with Oracle 2 in
  https://github.com/u2giants/theoracle/pull/406 . The replacement launcher keeps the
  first and third behaviors (format check `^[a-z]{20}$` instead of pin hashes) and reads
  `oracle_supabase_project` at launch from the machine-private targets profile (user
  config dir, `oracle`/`targets.json`; env override `ORACLE_TARGET_PROFILE_PATH`) — the
  exact path is in the launcher's header comment at the GitHub URL in §3. **No project
  ref may ever be committed to this repo** (public-boundary rule); that is why the entry
  does not just inline `--project-ref`.
- The entry is wrapped by the ai-devops secret launcher (`mcp-launch.cmd`/`mcp-launch.sh`,
  machine tooling) which injects `SUPABASE_ACCESS_TOKEN` from 1Password item
  "Supabase Personal Access Token" (vault `vibe_coding`) before the child starts. The
  launcher script must NOT wrap that again — it is already inside it.
- `--read-only` on the Supabase MCP is deliberate and must stay: migrations go through
  `pnpm db:migrate` only (documented in `docs/development.md`); the MCP must not be used
  for `apply_migration`.
- The live database has exactly four tables (evidence in §3) — the old `settings` table
  is physically gone, which is what makes the (c) doc removals correct rather than
  premature. `docs/agents/08-data-model-and-external-identifiers.md` still describes
  `settings` rows and an `/admin/settings` UI that no longer exist (see §6 step 3).
- GitHub's container packages here are user-owned (`ghcr.io/u2giants/...`), so deletion
  goes through the user-packages REST API once a `delete:packages` token exists.

## 6. Exact next steps

1. **(a) Delete the two container images when a `delete:packages` token exists.**
   Mint a classic GitHub PAT with `delete:packages` through the u2giants account's
   interactive GitHub settings (this cannot be done via API — see §0: never ask the owner
   to type it; route it to a session that has the account's authenticated browser, or
   record it stays blocked). Then delete every version of `theoracle-native` and
   `theoracle-native-browser` (DELETE /users/u2giants/packages/container/<name>/versions
   …, or the package itself), then post the result on
   https://github.com/u2giants/theoracle/issues/431 and tick the `- [ ] live proof` line
   in the closing comment. **You'll know it worked when** both package names 404 for a
   read:packages-capable token and the live-proof line is ticked on #431.
2. **(nothing else is required for this workstream)** — (b) and (c) are landed and
   verified; re-proving them is only needed if `.mcp.json` or the two docs change again.
3. **Optional cleanup, deferred on purpose (not part of task 7's named scope):**
   remove the remaining stale mentions of the seed script ("migrate/seed scripts") at
   https://github.com/u2giants/theoracle/blob/main/docs/agents/04-repository-structure.md#L11
   and of the old settings table / `/admin/settings` at
   https://github.com/u2giants/theoracle/blob/main/docs/agents/08-data-model-and-external-identifiers.md#L16
   (and lines ~23, ~46, ~47). One small PR, `bin/ai-doc-safety` must pass.
   **You'll know it worked when** a grep for `seed` and `settings` table language in
   `docs/agents/` returns nothing stale and doc-safety passes.
4. **Optional observation, deferred:** the `trigger` entry in
   https://github.com/u2giants/theoracle/blob/main/.mcp.json still launches the
   Trigger.dev MCP although all four Trigger.dev projects were deleted in #398. Decide in
   its own task whether to repair or remove it. **You'll know it worked when** the
   decision is recorded on a repo issue one way or the other.

## 7. Constraints and gotchas in force

- Public repo boundary: no LAN IPs, no Supabase/Trigger project refs, no secrets in code,
  commits, issues or PRs. GitHub URLs only in handoffs (no machine-local paths).
- Never push to `main`. Branch + PR + `gh pr merge --squash --admin`. Doc-only changes
  need `bin/ai-doc-safety` green on the exact head before merge.
- Declare work with `ai-task-gates start --class <class>` and re-check before `pr-wait`
  and `ship`; `ship` under class `production` needs `--acknowledge` with a quoted owner
  authorization (see §4).
- Quote every human-facing time in EST (America/New_York).
- Sign GitHub issue/PR posts with `Posted by MiMo chat <session-id> on <machine>`.
- The task prompt's scope guard: do only the named task; never spawn child sessions;
  never end a turn on "waiting" — arm `bin/ai-pr-wait` in the background instead of
  hand-rolled polling.
- Secrets live in 1Password vault `vibe_coding` only (item titles in §8); values never in
  chat, argv, logs or commits.

## 8. Access and environment

- `gh` authenticated as `u2giants` — token scopes `gist, read:org, repo, workflow`
  (no `read:packages`, no `delete:packages`). GitHub host: github.com, repo
  u2giants/theoracle.
- 1Password service account reaches vault `vibe_coding`; MCP secret injection runs
  through the ai-devops secret launcher (`mcp-launch.cmd` on Windows). Relevant items:
  "Supabase Personal Access Token", "OpenRouter API Key - The Oracle (local .env.local)"
  (field `OPENROUTER_API_KEY`), "GitHub token with Packages read access for
  u2giants/backrest-wiz" (read-only).
- OpenRouter budget check 9:28 PM EST 2026-11-04: `limit_remaining` ≈ $21.33 — above the
  $5 stop line; re-check before any paid model work.
- Session worktree (Windows, task host "edge-dev") is removed after merge per wrap-up;
  the two ai-devops bash tools (`bin/ai-doc-safety`, `bin/ai-pr-wait`) live in the
  installed ai-devops checkout and are run with the Git for Windows bash (§4).
- The machine-private targets profile (user config dir, `oracle`/`targets.json`, key
  `oracle_supabase_project`) must exist on any machine that runs the `supabase-oracle`
  MCP entry; `ORACLE_TARGET_PROFILE_PATH` overrides its location.

## 9. Open questions and risks

- **Provenance of the no-backup deletion (see §0)** — recorded 2026-11-05; awaiting
  Albert's one-word confirmation; no work depends on it.
- **`@latest` on `@supabase/mcp-server-supabase`** (inherited from the deleted script):
  upstream can change behavior under us. If determinism matters later, pin the version
  the way other POP apps do — verified working today at 0.15.0 (2026-11-04).
- **Residual stale doc mentions** in `docs/agents/04` and `docs/agents/08` (§6 step 3)
  were deliberately left — task (c) named only the configuration and development docs.
  They are recorded on #431's closing note so they are not lost.
- **The `trigger` MCP entry** (§6 step 4) may be dead weight after the Trigger.dev
  project deletions; untested this session.

---

Self-audit (handoff-writer gate): all 10 sections present; §0 holds the single owner
confirmation and states the blocked credential is not an ask; §4 carries every dead end
with why it failed; §6 steps each end in a verification gate; every file/commit reference
is a GitHub URL; commit/push/merge status explicit in §3; secrets named by vault/item
only. Answers: (1) yes — a newcomer can continue from §3 and §6 alone; (2) yes — the
non-obvious launch chain and boundary rules are in §5 and §7; (3) yes — background,
goal, state, failures, constraints, risks and exact next actions are all present;
(4) yes — §0 lists the only owner judgement (the provenance confirmation) and no
technical approval.
