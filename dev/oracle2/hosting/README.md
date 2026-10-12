# Isolated native executor boundary

Owner: Oracle W11 coordinator on existing issues #27/#58. This boundary supports
the proposed safety-preserving replacement of direct shared-tailnet access.
It does not deploy resources, obtain permission, run company questions, restart
grading, or admit private source processing.

## Capability and authority

Trigger remains the dedicated orchestration project. Native Python/GraphRAG SDK
execution, custody, ledger and candidate graph remain within an app-owned Coolify
namespace. The executor has no Tailscale, Trigger, Coolify, OpenRouter, confirmed,
checkpoint or administrator credentials. No graph/ledger port is published.
Separate confirmed storage remains unreachable to the candidate executor.

This changes the previous direct Trigger-to-SDK placement. The coordinator must
update both plans and obtain an independent exact-input architecture/security
approval before release. A public authenticated job ingress is a new component;
it must not become a public private-data or general administration endpoint.
App authentication alone does not repair wildcard tailnet grants.

## Ingress API

`OpaqueGateway` requires a client certificate from its configured CA, exactly
one URI SAN matching its dedicated worker identity, and an HMAC signature over
`POST`, a newline, the fixed request path, another newline and the exact request
body. Signatures cannot cross between admission and result delivery. TLS requires client authentication and hostname/CA
verification in the client. Request handshakes take at most five seconds and
at most 32 connections can be handled concurrently.

`POST /v1/jobs/admit` and synthetic-only `POST /v1/jobs/result` accept an opaque
JSON object with exactly these fields:

- `job_id` and `nonce`: canonical UUIDs.
- `runtime_hash` and `admission_hash`: lowercase SHA-256 digests.
- `expires_at`: an integer strictly after current time, at most 120 seconds ahead.

`X-Oracle-Job-Signature` is HMAC-SHA256 of the method/path/body domain using the independently
reviewed gateway signing credential. Body size is at most 2048 bytes. Duplicate
JSON keys, duplicate length/signature headers, transfer encoding, private text,
URLs, query strings, alternative routes and client identities are refused.

The trusted `admit(OpaqueJob, worker_uri)` callback must atomically validate the
current authoritative job registry, exact actor/workspace/run/scope, runtime and
admission seals, source permission, lease, revocation and one-use nonce, then
persist/enqueue only the opaque job or raise. There is no permissive default.
Parameters and originals stay in the native ledger/blob custody layer.
Response 202 contains only `job_id`, `request_hash` and `state=accepted`.
Enqueue is not execution or delivery. Synthetic-only result delivery holds
current canonical job/source/release authority, shares global one-use nonce
protection, and returns either empty pending status or the exact stored canonical
pack bytes within the sealed query budget and global 131072-byte envelope. The
delivery lease is bounded to five seconds. Private result serving remains denied.
No generic original serving is supplied here.

## Internal provider egress

`EgressServer` listens only on the isolated provider network, using mutual TLS
and one exact executor URI. Never publish or attach it to public ingress.
Only `POST /v1/provider/chat` exists, with a maximum two-megabyte JSON body.

`ReservedEgress` accepts exactly `reservation_id`, `request_hash` and `request`.
It hashes canonical actual request bytes. Exact models are configuration-pinned;
the provider endpoint is fixed to OpenRouter chat completions, routing only to
OpenAI with fallback disabled, data collection denied, storage false, bounded
completion tokens and streaming disabled. URL overrides, proxy CONNECT,
environment proxy routing, redirects and automatic retries are unavailable.

Trusted `reserve(id, digest, bytes)` must return a context manager that verifies
the actual global reservation, price/cost bound, actor, permission and request
seals, and atomically writes a one-use dispatch intent. Unavailable, ambiguous,
expired or repeated reservation state must refuse dispatch. Trusted
`settle(id, digest, raw_response)` must validate actual usage; unknown failures
retain the reservation. These callbacks are required and are integration gates,
not implementation of account-wide reservation coverage.

## Namespace and exact release inputs

`topology.yaml` contains architecture inputs only. Its startup command requires
the coordinator-owned native runtime factories; it is not deployable before
those exist and the exact immutable application image and protected volumes
are admitted. No prior synthetic credential is a hosted credential. Do not
create production keys/certificates before exact independent issuance review.

The documentary image must use the dependency profile without the
`process-analysis` extra. Do not install/distribute the unqualified PM4Py/PuLP
solver distribution in that image. This preserves the separate analytical
source/profile and every bundled solver for subsequent qualification; it does
not prune vendor files or claim the analytical slice accepted.

All executor/store/provider internal networks require **both** `internal: true`
and IPv4/IPv6 `gateway_mode=isolated`. Ordinary internal mode alone leaves
host bridge access. Docker Engine must support isolated gateway mode; verify
the actual target rather than silently dropping the driver option. No privileged
mode, host networking, published store ports, Docker socket, mounted host source
directory or network administration capability is permitted. Coolify owns these
application networks; any host upgrade belongs to the separately governed
Ansible path.

Candidate/confirmed images retain the exact existing FalkorDB digest; its
inspected native module location is `/var/lib/falkordb/bin/falkordb.so`.
Postgres uses its existing pinned digest. Secret server configuration and
password files belong to protected platform volumes, never command arguments.
Ingress TLS routing must preserve client certificate verification: do not
terminate mTLS at a proxy that discards authenticated client identity.

## Verification and unresolved release obligations

`test_hosting_boundary.py` exercises actual invented-source mutual TLS ingress
and broker requests, idle untrusted TCP, unrelated client certificates, signed
private payload rejection, replay, revocation, runtime drift, invalid envelopes,
unreserved egress and settlement order. No paid/private provider call occurs.

`verify_namespace.py --owner <unique-owner> --result <protected-result>` creates
only its own labeled synthetic containers using a pinned Node image. It refuses
existing names, observes an allowed internal peer, then tests denied shared
control-plane/SSH, IPv4/IPv6 internet and unrelated container access. It asserts
no bridge gateway, no ports, no privileged capability and no mounted host path.
It preserves exact inspection before stopping its containers; it deletes nothing.
This is local namespace proof, not target deployment proof.

Before closure, prove the target's exact image, platform inputs, TLS identity,
namespace inspection, negative checks, independent native factory/current ledger
admission, reservation enforcement, cold/warm execution, permission revocation,
source custody, SDK finalize/reload, checkpoint and fresh restore/rebuild,
authorized view delivery and preserved legacy web/worker capability. Keep live
proof on the same existing issues. Company questions and grading remain paused.

Official references:
[Docker isolated gateway mode](https://docs.docker.com/engine/network/port-publishing/),
[Tailscale grants](https://tailscale.com/docs/reference/syntax/grants),
[Tailscale IP set limitations](https://tailscale.com/docs/features/tailnet-policy-file/ip-sets),
[Tailscale management scopes](https://tailscale.com/docs/reference/trust-credentials).

### Fixed native startup and current metadata authority

`python -m oracle_brain.hosting.runtime validate` is import/profile validation,
explicitly **not** live admission. `gateway` and `executor` load only a fixed
operator settings file (`ORACLE_HOSTING_SETTINGS`, default
`/run/oracle-auth/settings.json`). `ORACLE_HOSTING_SETTINGS_SHA256` must pin its
exact bytes outside HTTP. Each file, TLS key/CA/certificate, database URL and
HMAC key must be private regular files; symlinks/public files fail closed.
The database connection must use `sslmode=verify-full` plus a protected CA.
The gateway has only the new ledger's dedicated metadata login. The executor
has a distinct application login and private blob root, never a gateway secret.

Common exact settings keys: `profile`, `runtime_hash`, `synthetic`,
`allowed_release_hashes`, `worker_uri`, `database_url_file`, `registry`,
`registry_hash`, `spool`. Gateway additionally requires `server_cert`,
`server_key`, `client_ca`, `hmac_key_file`, `bind_host`, `bind_port`.
Executor additionally requires `graph_url_file`, `blob_root`. No arbitrary
factory/module/callback name is accepted. Unknown keys/profiles are denied.

The separately pinned registry is policy only, with exact keys `worker_uri`,
`runtime_hash`, `active`, `expires_at`, `allowed_release_hashes`. Its canonical
contract digest is `registry_hash`. It contains no original text, job payload,
private result, workspace permission, or static per-job allowlist.
`job_id` is the existing native view/action run UUID. `admission_hash` equals
that selected release's documentary gate hash. The current PostgreSQL resolver
supplies workspace, actual run, scope and expiry after validating independently
allowed release hashes, selector, watermark, artifact seal/dependencies,
source revision/provenance and owner-rooted current source appointments.
Finding-review additionally checks the exact bounded scope appointment. The
executor separately checks actual private finding membership and delivery.
Unregistered semantic verification and event import jobs remain denied.

Apply `sql/006_hosting_gateway_authority.sql` only to a newly issued dedicated
Oracle application ledger after exact independent review. It creates a NOLOGIN
metadata group, denies elevated/reused membership, grants bounded columns,
and exposes finding scope through a fixed security-definer metadata function.
It never grants view packs/query plans, source reading/receipt bodies, action
notes/payload/results, private blob keys, writes or arbitrary function execution.
The independently issued LOGIN must be nonsuperuser, no bypass RLS, no role
creation, no database creation, no owner membership and only the metadata group.
Public schema/default privileges must be reviewed on the actual new ledger.
Gateway joins isolated ledger network with authenticated PostgreSQL TLS; raw
stores remain unpublished. No actual role issuance or deployment is implied.

Custody requires this resolver and authorizer. A shared filesystem lock, durable
nonce marker and exclusive pending file prevent duplicate enqueue/replay;
current authority is held across enqueue and claim. The native executor repeats
current authority before private access, then executes only retained `run_view`
or finding-review `run_event`. Synthetic fixed embeddings are available only
for an exact synthetic release/profile. Private execution intentionally fails
until a qualified fixed embedding admission is integrated; no business
question generation or grading is resumed by these profiles.

### Reproducible executable synthetic hosting assets

`prepare_synthetic.py` requires an explicit synthetic flag, a fresh protected
output directory, immutable local native image ID, exact runtime hash and one
or more externally supplied release hashes. It creates only a new local test
namespace. It never reads an existing deployed URL, management key, provider
key, Tailscale identity, original source or production credential. It generates
short-lived synthetic CA/server/worker certificates (including strict X.509
key identifiers/usages), separate PostgreSQL passwords, separate candidate and
confirmed graph passwords, protected settings, a policy-only registry, a fixed
schema/bootstrap SQL set and an executable Compose file. Candidate auth uses
the existing SDK-compatible isolated-network Redis path; this is **not** a
claim of qualified SDK TLS support. Executor receives no confirmed credential.

For a non-root developer the generator uses a uniquely named, networkless,
read-only pinned Python helper with one mount: the freshly created synthetic
asset directory. It sets only the required container-user ownership there.
The helper is retained stopped; no container, volume or evidence is deleted.
Synthetic issuer/grants are authorized only for this new local marked ledger,
never production. Gateway gets the bounded metadata role; executor gets only
application table CRUD/sequence usage, no schema creation/DDL/admin powers.
The broker's separate dormant login gets only reservation/receipt/diagnosis
SELECT+INSERT and `pg_control_system` execution. Its provider profile, source
column grants, provider key, witnessed coverage and paid dispatch remain absent.
No broker service is started by the synthetic Compose file. Production topology
retains its provider service behind the `provider-admitted` profile until its
fixed reviewed startup exists; this is an open dependency, not a completed fix.

`verify_synthetic.py` examines and exercises the actual generated five-service
stack. It requires the synthetic marker and verifies all services running,
IPv4/IPv6 isolated private networks, verified gateway worker mTLS, rejection of
missing certificates and signed-but-unregistered opaque jobs, verified ledger
TLS, restricted gateway columns/writes, authenticated candidate connectivity,
and executor denial of internet IPv4/IPv6, shared Coolify/SSH and the confirmed
namespace. Its protected receipt explicitly records `native_job_acceptance:
false` and `provider_dispatch: false`. Placeholder fixture release hashes
exercise denial/startup only; they never qualify a real release or job.

Before stopping local stacks, preserve exact inspect records, PostgreSQL dump,
graph checkpoint files and protected settings/keys. Stop only those unique
project resources and retain volumes. Do not use `compose down -v` or delete
another session's resources. Live deployment still requires independently
reviewed exact source/image inputs, new owned app resource/roles, trusted TLS
routing, protected real admission registry, qualified original-source/embedding
admission, witnessed provider key coverage and live native acceptance. Company
questions and grading remain paused throughout.

## Fixed public invented release preparation

See [SYNTHETIC_BOOTSTRAP.md](SYNTHETIC_BOOTSTRAP.md) for the fixed seed,
networkless per-volume bootstrap, raw Application inputs, exact native service
identities and the remaining independent action/live-proof gates.
