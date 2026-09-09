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
assert_blocked 'owner request cannot bypass protected migration' --owner-request 'fixture owner request'

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

if [ "$failures" -ne 0 ]; then
  printf '%s failure(s)\n' "$failures" >&2
  exit 1
fi
printf '%s passed / 0 failed\n' "$passes"
