# Native v2 transport source proof

Source-only implementation based on fb94fb79, October 18, 2026 EDT. No credential, cloud setting, SQL authority, projection or native job was created or changed.

The additive v2 web adapter is selected only by `ORACLE2_NATIVE_TRIGGER_MODE=v2`; original v1/default paths remain. The corresponding-source delivery endpoint is generic and unchanged. New web constants/source refs use the canonical public identity JSON. Metadata requires the exact v2 database, gateway login/default group, one group, strict role flags, current source/release/artifact/expiry. Admission retains durable SQL dispatch before Trigger; final delivery compares canonical bytes and full attestation. Empty requests retain one-byte/one-second framing checks before metadata.

The isolated v2 worker/config keep task `oracle2-native-invented-v2`, Node24, maxDuration120, retry1, exact public opaque IDs and no text payload. The task refuses old bundles/provider/admin/projector credentials, including empty environment values; validates complete output and current expiry. Legacy config explicitly excludes v2; each scoped config dynamically excludes all unrelated tasks.

Executed checks:

- `pnpm --filter @oracle/web exec tsx --test lib/native-trigger-v2.test.ts lib/native-trigger.test.ts`: 27 passed. Real installed Next adapter covers empty/nonempty/unfinished streams; handler tests cover admission replay, canonical bytes and counterfeit output refusal.
- `pnpm --filter @oracle/workers exec tsx --test oracle2-native-v2-config.test.ts oracle2-native-config.test.ts`: 22 passed, each a real config subprocess import.
- `pnpm --filter @oracle/workers exec tsx --test oracle2-native-v2-task.test.ts`: 4 passed; fixed identity alignment, explicit independent forbidden-variable list, complete/current attestation negatives.
- Web and worker `tsc --noEmit`: passed.
- Actual `node scripts/oracle2/verify_worker_bundle.mjs`: passed existing five task/config pairs. Coordinator owns adding the sixth v2 pair and full corresponding-source offer after integrating the separate v2 Python module; this source-only result does not claim that integration or live acceptance.

Logs retained privately by the coordinator in session scratch. Root performs independent review, combined bundle/source checks, normal PR/CI/merge, deployment and live proof separately. No push or PR was made by this implementation lane.
