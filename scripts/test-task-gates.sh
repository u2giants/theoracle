#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cd "$ROOT"

failures=0
passes=0
pass(){ passes=$((passes + 1)); printf 'PASS: %s\n' "$1"; }
fail(){ printf 'FAIL: %s\n' "$1" >&2; failures=$((failures + 1)); }

expect_class(){
  local path="$1" expected="$2" label="$3" actual
  printf '%s\n' "$path" > "$TMP/paths"
  actual="$(ai-task-gates explain --json --paths-from "$TMP/paths" | jq -r '.observed_class')"
  if [ "$actual" = "$expected" ]; then pass "$label"; else fail "$label (expected $expected, got $actual)"; fi
}

expect_class README.md prose 'ordinary documentation uses the prose fast path'
expect_class apps/web/app/page.tsx code 'ordinary source uses the code path'
expect_class AGENTS.md reviewer-safety 'agent rulebook receives protected full treatment'
expect_class .ai-devops/task-gates.json reviewer-safety 'task-gate policy protects itself'
expect_class scripts/test-task-gates.sh reviewer-safety 'task-gate assertion protects itself'
expect_class MACRO_FIRST_IMPLEMENTATION_PLAN.md reviewer-safety 'canonical forward plan receives protected full treatment'
expect_class MACRO_FIRST_REDESIGN.md reviewer-safety 'macro redesign contract receives protected full treatment'
expect_class SHAPE_AWARE_READER_DESIGN.md reviewer-safety 'shape-aware design receives protected full treatment'
expect_class oracle_master_spec.md reviewer-safety 'master product specification receives protected full treatment'
expect_class vercel.json deployment 'Vercel release contract is protected deployment work'
expect_class package.json deployment 'delegated Vercel build command is protected deployment work'
expect_class apps/web/package.json deployment 'web build package contract is protected deployment work'
expect_class packages/ai/package.json deployment 'production guard package contract is protected deployment work'
expect_class scripts/verify-vercel-contract.mjs deployment 'Vercel contract guard is protected deployment work'
expect_class apps/workers/trigger.config.ts deployment 'Trigger worker configuration is protected deployment work'
expect_class packages/db/migrations/20990101000000_fixture.sql shared-db 'migration is protected database work'

fixture="$TMP/theoracle"
git -C "$TMP" init --quiet theoracle
git -C "$fixture" config user.name 'Task Gate Test'
git -C "$fixture" config user.email 'task-gate-test@example.invalid'
git -C "$fixture" remote add origin https://github.com/u2giants/theoracle.git
mkdir -p "$fixture/.ai-devops"
cp "$ROOT/.ai-devops/task-gates.json" "$fixture/.ai-devops/task-gates.json"
git -C "$fixture" add .ai-devops/task-gates.json
git -C "$fixture" commit --quiet -m baseline

export AI_TASK_GATES_DIR="$TMP/state"
(
  cd "$fixture"
  ai-task-gates start --class code --base HEAD >/dev/null
  mkdir -p packages/db/migrations
  printf '%s\n' '-- classification fixture only' > packages/db/migrations/20990101000000_fixture.sql
)

assert_blocked(){
  local label="$1"; shift
  local output rc
  set +e
  output="$(cd "$fixture" && ai-task-gates check --before ship "$@" 2>&1)"
  rc=$?
  set -e
  if [ "$rc" -eq 3 ]; then pass "$label"; else fail "$label (exit $rc: $output)"; fi
}

assert_blocked 'migration scope escalation refuses shipping'
assert_blocked 'acknowledgement cannot bypass protected migration' --acknowledge 'fixture acknowledgement'
# Assert argument refusal itself; a migration refusal cannot mask flag acceptance.
set +e
legacy_output="$(cd "$fixture" && ai-task-gates check --before ship --owner-request 'fixture owner request' 2>&1)"
legacy_rc=$?
set -e
if [ "$legacy_rc" -eq 1 ] && [ "$legacy_output" = 'ai-task-gates: error: unknown option for check: --owner-request' ]; then
  pass 'legacy owner request flag is refused'
else
  fail "legacy owner request (exit $legacy_rc: $legacy_output)"
fi

(
  cd "$fixture"
  rm -f packages/db/migrations/20990101000000_fixture.sql
  mkdir -p apps/web/app
  printf '%s\n' 'export default function Fixture(){ return null }' > apps/web/app/page.tsx
  ai-task-gates start --class code --base HEAD >/dev/null
  ai-task-gates check --before ship >/dev/null
)
pass 'valid code flow proceeds to shipping checks'

cp "$fixture/.ai-devops/task-gates.json" "$TMP/policy.backup.json"
rm -f "$fixture/.ai-devops/task-gates.json"
printf '%s\n' 'vercel.json' > "$TMP/rollback-path"
without_policy="$(cd "$fixture" && ai-task-gates explain --json --paths-from "$TMP/rollback-path" | jq -r '.observed_class')"
cp "$TMP/policy.backup.json" "$fixture/.ai-devops/task-gates.json"
with_policy="$(cd "$fixture" && ai-task-gates explain --json --paths-from "$TMP/rollback-path" | jq -r '.observed_class')"
if [ "$without_policy" = code ] && [ "$with_policy" = deployment ] \
  && cmp -s "$TMP/policy.backup.json" "$fixture/.ai-devops/task-gates.json"; then
  pass 'rollback removes the local escalation and byte-exact restore reinstates it'
else
  fail 'rollback positive control or source-integrity check failed'
fi

# Selected tooling contains public code only. The repository opts into the
# sealed attachment route; whole-repository review and runtime writes stay shut.
(
  cd "$fixture"
  ai-task-gates start --class private-tooling --base HEAD >/dev/null
  ai-task-gates check --before code-only-review >/dev/null
)
pass 'private tooling admits the sealed synthetic-fixture review route'
if (cd "$fixture" && ai-task-gates explain --json | jq -e '.required_gates|index("repository-workflow-compliance")!=null' >/dev/null); then
  pass 'private tooling retains repository workflow compliance'
else
  fail 'private tooling lost repository workflow compliance'
fi
for action in review deploy database infrastructure production shared-db-promotion; do
  set +e
  output="$(cd "$fixture" && ai-task-gates check --before "$action" 2>&1)"
  rc=$?
  set -e
  if [ "$rc" -eq 3 ]; then pass "private tooling still refuses $action"; else fail "private tooling $action (exit $rc: $output)"; fi
done
(
  cd "$fixture"
  ai-task-gates start --class private-evidence --base HEAD >/dev/null
)
set +e
output="$(cd "$fixture" && ai-task-gates check --before code-only-review 2>&1)"
rc=$?
set -e
if [ "$rc" -eq 3 ]; then pass 'private evidence remains outside the tooling exception'; else fail "private evidence review (exit $rc: $output)"; fi

# A stronger tooling declaration cannot launder a changed licensed path.
(
  cd "$fixture"
  mkdir -p fixtures/licensed
  printf '%s\n' '{}' > fixtures/licensed/synthetic.json
  ai-task-gates start --class private-tooling --base HEAD >/dev/null
)
set +e
output="$(cd "$fixture" && ai-task-gates check --before code-only-review 2>&1)"
rc=$?
set -e
if [ "$rc" -eq 3 ]; then pass 'changed licensed evidence defeats a tooling declaration'; else fail "licensed tooling laundering (exit $rc: $output)"; fi
rm -f "$fixture/fixtures/licensed/synthetic.json"

# The attachment exporter must also refuse a legacy app fixture even though
# its pre-existing naming does not match the central licensed-directory rule.
mkdir -p "$fixture/apps/workers/src/__fixtures__"
exporter="$(dirname "$(readlink -f "$(command -v ai-task-gates)")")/ai-review-code-only.py"
for extension in json ts mjs; do
  selected="apps/workers/src/__fixtures__/licensed-synthetic.$extension"
  printf '%s\n' '{}' > "$fixture/$selected"
  printf '["%s"]\n' "$selected" > "$TMP/private-paths.json"
  set +e
  output="$(python3 "$exporter" create "$fixture" "$TMP/refused-export-$extension" "$TMP/private-paths.json" --base HEAD 2>&1)"
  rc=$?
  set -e
  if [ "$rc" -ne 0 ] && ! compgen -G "$TMP/refused-export-$extension*" > /dev/null && [[ "$output" == *'evidence or hidden path refused'* ]]; then
    pass "legacy app fixture with $extension suffix cannot enter sealed code export"
  else
    fail "licensed exporter refusal ($extension, exit $rc: $output)"
  fi
  rm -f "$fixture/$selected"
done

if [ "$failures" -ne 0 ]; then
  printf '%s failure(s)\n' "$failures" >&2
  exit 1
fi
printf '%s passed / 0 failed\n' "$passes"
