# Native synthetic source qualification

Owner: Codex coordinator, issue #27 and proof card #58. October 12, 2026, 3:55 PM EDT.

Exact implementation head `8ea5ab8b8174d15f2365bc2ca9ce07e0bed4c0d2` passed the mandatory W10 synthetic harness: 510 tests, zero skips, zero failures. Receipt SHA256 `0906b1715679a1a69fc854a863e5aa299cedd9444d91b6868247fd7b3f08061e`; implementation/test input hash `ffc4a48e31c12bce624648cb3dbb768ea2fc0f56759cec6cb405799568e3e575`; JUnit SHA256 `3bdb4800fa887e0604dccc7c835360845a9de510e5052548cf52585fc187799e`. Versions: `{"graphrag-sdk": "1.4.0", "langgraph": "1.2.12", "psycopg": "3.3.6", "pydantic": "2.13.5"}`. Head and clean source tree were checked before and after the run; bytecode writing was disabled. Protected receipt and fixture custody remain local; no private originals were supplied to these tests.

The combined gate includes actual registered-projector TLS/SCRAM source-role binding, native SDK 1.4.0 ingestion/finalization, public two-source artifact and record-digest equality, exact projector data-plus-ontology ACL, foreign graph denial, executor read-only data and ontology access with mutation and foreign-namespace denial. The deployed issuer uses the same tested ACL builder. Its literal `__ontology` suffix and SDK version are pinned; drift refuses issuance. The projector keeps the stock native SDK and its per-artifact ontology capability. The executor may read only the selected artifact data graph and its exact `__ontology` sidecar; writes remain denied. The app-owned SDK adapter routes both data and ontology reads through the stock native read-only decoder and loads the persisted ontology without registering it. A full registered NOINHERIT executor test now covers TLS/SCRAM, documentary completion, identical warm result reads and denied completion replay, positive stock-SDK retrieval, denied mutations/foreign namespaces, and fail-closed missing ontology. This isolated test is not hosted acceptance.

Independent review of the preceding implementation found missing projector source binding; a real end-to-end test reproduced that refusal and then exposed the native SDK sidecar requirement. Both are repaired, and that test is mandatory. Earlier 501-pass proof did not exercise the projector entry point and is not sufficient for this implementation. The previous review was retained non-authorizing after concurrent tests created an untracked bytecode cache; root preserved that cache outside the source tree, adopted its substantive REJECT finding, and will obtain a fresh exact-head review. No stale review is shipment authority.

Docker Compose interpolation also checks every per-profile bundle name and resource-UUID-specific router/network, the gateway DNS SAN and platform image/hostname settings. Remote platform rendering is a separate gate. Mandatory missing-fixture failure remains; no test is converted to a skip.

Live production-host READ ONLY inventory, independently action-reviewed, observed 12 Docker networks, with no overlap against the four prospective IPv4/ULA pairs. Native inspect SHA256 `79753f6c2b25982a92ec81a4b105abeb99cc09a5f59c7d9a639041effa1aab32`; reviewed operator SHA256 `4a508f246d2dc2b5372b6071cf91f167aeb164aa839100fa478777b24c89e72f`. Existing account password authentication worked without changing policy, known-hosts, credentials or host configuration. This is network-admission evidence, not installation.

Coolify recovery must use its managed application action with `docker_cleanup:false`; official v4.4.6 still removes containers and connected networks while retaining named volumes. It is **not literal stop-only**. Exact action review must include backups and recoverable container/network removal; no deletion of named volumes or host changes is authorized.

Source merge, immutable image publication, isolated namespace creation, credential issuance, platform deployment, external mTLS request/result bytes, restore/restart, private semantic acceptance and business acceptance remain separate gates. Current published image belongs to earlier PR #95/main and is not authority for this implementation. PM4Py/PuLP remains separately unqualified for product bundling.

The existing event-service CI token returned 401; the valid D1 read token is active but Workers and own-token permission metadata return 403. No existing authorized account session was found. CI provider key differs from Oracle; running-service key remains UNKNOWN. No token substitution, scope expansion, new paid calls or company-data adoption occurred.

Downstream review: W01-W12 acceptance and S03-S16 dependencies remain open. Original-region custody is local preparation and does not issue current SourceRefs or semantic acceptance. Company questions, employee messages and grading remain paused.

## Native image CPU portability gate

The PR102 image90eaa56528de5fd15f58117927ffa0fc80136789bcd67ffbd5e76edc0f8839ac
exits132 (SIGILL) on edge-dev3 when importing hnswlib0.8.0; a faulthandler
reproduction isolates GraphRAG1.4.0's optional native-resolution import to that
module. The fresh networkless issuer stopped before creating assets; its spent
claim and container remain preserved. No new authority was minted or installed.
The pinned upstream hnswlib0.8.0 setup defaults to -march=native and supports
HNSWLIB_NO_NATIVE to omit builder-specific ISA tuning. This is a source build
portability defect consistent with the observed SIGILL; the exact offending
instruction and earlier image's build-host history remain unknown.

The image build uses that supported build-only flag before frozen uv sync.
No dependency removal, version downgrade, stub, fallback, vendor patch or
runtime search suppression. The final shipped profile additionally imports
the stock SDK, creates a real native ANN index over three invented vectors,
verifies nearest-neighbor results and saves/reloads the index with identical
results under the runtime UID. A publisher result still requires actual
non-builder-host execution of the immutable artifact before installation.
Upstream source: https://github.com/nmslib/hnswlib/blob/v0.8.0/setup.py#L67-L111.

`coolify-native-preflight.yaml` provides a separately reviewed normal-platform
one-shot proof of that exact immutable artifact on the deployment host before
credential issuance. It runs only the public invented ANN qualification, under
UID10001, network-none, read-only root, dropped capabilities, no-new-privileges,
CPU1/1GiB/128PIDs/core0 and a bounded writable tmpfs. No ports, volumes, stores,
credentials, provider inputs or data admission. The app-owned preflight uses the
existing empty inert app and has a distinct Compose namespace; its exact
managed configuration/start and later full-runtime configuration require
separate source/input action approvals. Target exit0 plus fixed public receipt
and actual OCI/resource readback qualify the artifact, not documentary job or
private/business acceptance. Preserve stopped proof/receipt before any managed
transition; old failed apps, stores and spent leases remain untouched.

### Managed preflight empty-command serialization — October13,2026,8:00AM EDT

The first managed credential-free preflight apphrnrhqkvutqkimfsqrygvyad/deploymentgfo7oyuzbfdd0zaqjhehinuc failed before the ANN service ran. Actual platform-parsed compose converted source `command: []` to an empty mapping `{}`; Docker rejected that mapping (`services.native-ann-proof.command must be a null`). The complete failed receipt SHA212defb96134688192c651e6dd4032f7995a74530433bce5ddb0dd2e9e1e86c6 and spent start marker remain preserved. No hosting credentials were issued and no target-host ANN success is claimed. Replace the empty sequence with Compose’s supported empty string, which suppresses the image default command while retaining the exact fixed ANN module entrypoint. All stock search/persistence capability and confinement are retained. A fresh separately reviewed managed attempt is required; this source repair alone is not target-host proof. Company questions/reports/employee messages and grading remain paused.

### Fixed preflight tmpfs scalar — October13,2026,8:20AM EDT

The exact create-action review at8033de4 identified an additional source-format defect before a new preflight start: unquoted commas in a flow-list split the intended single `/tmp` mount/options into four strings. Creation approval was conditional and did not authorize start; root did not execute that new create. Quote the complete scalar so one64MiB writable noexec/nosuid temporary mount survives YAML serialization. Keep every resource, network, filesystem and command bound. Verify the complete corrected source Compose locally with the real published stock SDK/index/persistence, rather than only manual Docker flags/config syntax; target-host proof remains distinct and required. Prior failed namespaces, spent markers and refused-task evidence remain preserved. Company questions/reports/employee messages and grading remain paused.
