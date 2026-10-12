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
the exact request body. TLS requires client authentication and hostname/CA
verification in the client. Request handshakes take at most five seconds and
at most 32 connections can be handled concurrently.

Only `POST /v1/jobs/admit` exists. Its JSON object has exactly these fields:

- `job_id` and `nonce`: canonical UUIDs.
- `runtime_hash` and `admission_hash`: lowercase SHA-256 digests.
- `expires_at`: an integer strictly after current time, at most 120 seconds ahead.

`X-Oracle-Job-Signature` is HMAC-SHA256 of the raw JSON using the independently
reviewed gateway signing credential. Body size is at most 2048 bytes. Duplicate
JSON keys, duplicate length/signature headers, transfer encoding, private text,
URLs, query strings, alternative routes and client identities are refused.

The trusted `admit(OpaqueJob, worker_uri)` callback must atomically validate the
current authoritative job registry, exact actor/workspace/run/scope, runtime and
admission seals, source permission, lease, revocation and one-use nonce, then
persist/enqueue only the opaque job or raise. There is no permissive default.
Parameters and originals stay in the native ledger/blob custody layer.
Response 202 contains only `job_id`, `request_hash` and `state=accepted`.
Enqueue is not execution or delivery. The coordinator must provide separately
authorized status/proof and existing view delivery paths; no generic result fetch
or original serving is supplied here.

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
