# Fixed forward-v2 platform staging proposal

Source preparation only. No platform request, credential issuance, deployment,
quiescence, backup, restoration, hosted proof, or acceptance is performed here.
The original application, source/image, expired certificates, registries and
spent job777 are untouched. Company activity stays paused.

## Supported platform source

Coolify v4.4.6 tag resolves to public commit
`f55efc859dfcbbf79274c4907b3df89f9767c11d`:

- `app/Http/Controllers/Api/ApplicationsController.php` allows the custom start
  field in application create/PATCH inputs.
- `app/Jobs/ApplicationDeploymentJob.php:755` validates that field, inserts the
  project directory if absent, and raw Compose startup executes it through the
  platform-owned helper. `write_deployment_configurations` writes the generated
  definition to the application's `docker-compose.yaml`.
- `bootstrap/helpers/docker.php:2021` injects compose/env flags into **only the
  first occurrence**. Every occurrence in our closed packet supplies all paths.
- `app/Support/ValidationPatterns.php:74` permits `&&` but excludes shell
  substitution. Pre/post hooks execute within an existing running app container;
  they are not a container staging route and are not used.

This is a source capability finding, not verification of the installed platform
helper, Docker Compose version, runtime labels, application or network state.

## Exact sequencing and retained gates

1. Independently review merged source/image, distinct platform project/environment,
   forward-v2 fixture/seal and unchanged bounded authority, source namespace and
   backup/restore namespace, selected public DNS, all role-specific bundles and
   expiry, and the existing genuine issuer-controlled browser actor/token.
2. Prepare source launch through normal seed Compose in a genuinely new app; its
   new materialization and authority have separate action admission. Cold/warm/
   restart, one completed canonical result and refusal proofs precede capture.
3. Separately create the restore Application with `instant_deploy=false` and the
   restoration source location. Read back its platform-assigned UUID. Compile a
   PATCH with that exact UUID and generated platform paths, image/source binding
   and original forward authority expiry. It creates all18, starts11 nonseed
   bootstrap profiles, waits for their successful completion, then starts only
   ledger/candidate/confirmed. Original seed Compose remains unchanged.
4. Restore ledger has no init-script mount or seed dependency. Its staging health
   accepts zero application relations; after restoration it requires exactly the
   forward-v2 marker and normal single-marker predicate. The ledger-init profile
   and gateway/executor/projector must remain CREATED. Independently observe
   empty stores, exact source/runtime, all18 identities, five role-bound physical
   networks, new volumes and original-authority byte bindings before mutation.
5. Independently admit source writer quiescence with storage still running; the
   existing recovery actuator deliberately supplies no stop/redeploy mechanism.
   Capture the complete canonical/result/source/roles/PG/custom dump/blob/spool/
   claim/nonce corpus. Restore only into the separately empty instance, compile
   roles only, preserve completed job/nonce bytes, rebuild through stock SDK from
   restored canonical artifact, reload through restricted reader and prove result
   delivery/caller isolation. No seed or spent admission/job replay.
6. Browser companion has its own source/image, private network and dedicated
   sealed auth configuration/action review. Source helper settings do not prepare
   its LOGIN membership, native-session settings or genuine owner token. It is
   not part of the fixed18 core contract or this restore staging proposal.

## Execution blockers remain explicit

Every phase has an exact fixed `sh -c` dual absolute-epoch guard, assembled only
from strict integer original-authority and separately genuine reviewer-action
lease expiries. Before first create both must retain more than300 seconds;
later phases require their fixed command timeout plus5-second kill budget and
15-second safety. Queue delay expires either guard before the phase dispatches.
No caller script, expression, clock override, eval, retry or renewal is admitted.

The compiler remains **NONAUTHORIZING**: root must independently prove report
identity and genuine current action lease association, one-use execution, and
actual helper sh/date/test/timeout/Compose-wait/pinned PHP-regex capability.
Pinned Coolify permits single-quoted script literals via its published regex;
PHP runtime is unavailable in the local qualification. Root owns actual platform
qualification. The fixed literal cannot self-attest reviewer authority.

## Local qualification

`test_hosting_restore_platform.py` proves closed literal commands, exact fixed
paths/roles, old/foreign/near-expiry refusal, unchanged normal Compose and all18
service contracts. Real local Docker Compose proves a failed one-shot makes
`wait` fail before store start. Two new networkless local PostgreSQL instances
prove empty-target observation, roles-only initialization, custom dump restore,
forward marker and invented result-byte parity, and unchanged job count. Actual shell-prefix checks prove valid guards pass and
queued original-authority expiry or expired reviewer lease refuses dispatch. Their
owned containers/anonymous volumes are removed. These are local source proofs;
no hosted/bootstrap/result/browser/reliability acceptance is asserted.
