# Native v2 official index-child regression

Owner: Oracle native-v2 transport lane; October18,2026 EDT. This fixture belongs to the v2 config test suite and retires with that scoped config. Source-only repair; no permission, provider call, deployment, task execution, database or graph mutation.

## Actual failure and producer

The authority-free038 cloud build failed before registering a worker. Read-only metadata proved two FAILED deployments, both worker-absent, and zero returned runs/no next page. The second deployment was deployment_gsadvaab2iv8km2reprky, version20261018.2, source038292d9977f548cacb5235e2c9d285f07147686. No native-v2 permission existed.

Installed official Trigger CLI4.5.15 explains the boundary: `managed-index-controller.js` fetches server environment variables and supplies `env: $env.data.variables` to `indexWorkerManifest`. That function forks the managed index worker using those variables and SDK indexing fields, without inheriting the controller's process environment. The generated Dockerfile exports TRIGGER_PROJECT_REF to the controller, but the child importing the config receives only the source-generated Python path. Therefore accepting that variable in the config was insufficient.

Before changing source, a local read-only/network-isolated Node24.21 Docker container executed the real official indexWorkerManifest function and the original038 compiled managed-index-worker. Correct parent project plus Python-only child variables reproduced exactly:

`Uncaught exception: Exact dedicated isolated native proof project required`

## Bounded repair

Only V2 config now defaults to the exact source-pinned isolated project when both override variables are undefined. Any defined wrong, shared, empty or conflicting override still fails. There is no indexing flag bypass, arbitrary target selection or additional runtime environment key. V1 config, all other tasks, native Python digest, maxDuration120 and retry1 remain unchanged.

The config itself is immutable reviewed target selection; an absent override is not missing runtime job authority. Actual task execution still requires the independently issued sealed v2 permission and all existing one-use/current-role/expiry gates.

## Executed portable regression

`pnpm --filter @oracle/workers exec tsx --test oracle2-native-v2-config.test.ts oracle2-native-config.test.ts` passed43 checks: existing v1 eleven plus v2 sixteen actual config imports and sixteen actual official Docker index-child cases. The default public Node24 Docker image was used for the final run; no host-specific image override was required. Missing overrides, correct custom/official and matching-both index only oracle2-native-invented-v2 at120 seconds/maxAttempts1. Wrong/shared/conflicting and all empty combinations fail even though the parent controller target is correct.

The test resolves public trigger.dev@4.5.15 dynamically via npx, asserts the version, then calls its local loadConfig/buildWorker APIs. It never runs CLI deploy, authenticates, reads a profile, fetches project settings or calls an API. An uncached CLI fixture may be downloaded from the public package registry. Temporary generated output is not committed. Docker executes the actual official fork and compiled managed-index-worker, read-only with network disabled; only Python path and deliberately public override test values enter the child. No task run is triggered. Qualified existing SDK/build/python dependencies remain4.5.15.

Worker typecheck and actual worker-bundle guard passed, including all six task/config paths and legacy exclusion. Native Python population remains638f6b3987021fb59ca76ad823ebfdab830db3c5c21d709784b4e239716876b5. Raw logs stay in coordinator-owned session scratch; source review, PR/checks/merge and separately reviewed build recovery remain coordinator work.
