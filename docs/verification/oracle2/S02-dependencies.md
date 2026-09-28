# S02 dependency and runtime qualification

Status: synthetic offline qualification passed at commit `3b94d22`; preview
qualification is still open. This is not a business-quality claim.

## Reproducible bundle

- Python 3.12.14; uv 0.12.19; `uv.lock` SHA-256
  `2c221d882eba1d52cb7a5d088a6647882f6c4054ec5c8ecaecf5346cf54dfbff`.
- Exported, hash-pinned worker `oracle2-requirements.txt` SHA-256
  `7e85bca540d8fd98f3be2f735d7cf1eefeaeb368205c80f95af08807001bebad`.
- Imported locally: graphiti-core 0.30.2, Docling 2.130.0, LangGraph 1.2.12,
  LangGraph Postgres checkpoint 3.1.2, FalkorDB Python 1.7.1,
  Pydantic 2.13.5, Torch 2.14.0+cpu, Torchvision 0.29.0+cpu.
- First unconstrained install measured 6.0 GB including CUDA libraries.
  Locked CPU-only Linux x86-64 variant measured 1.6 GB and imported all
  required packages. This is local disk size, not a Trigger build size or
  cold-start measurement.
- Compose image manifest digests: PostgreSQL 16.10-alpine
  `sha256:029660641a0cfc575b14f336ba448fb8a75fd595d42e1fa316b9fb4378742297`,
  FalkorDB v4.20.7
  `sha256:13996aa523f0dd283f6bd6df6620b094dcea525452417c4d6ef9bef15dc9998d`,
  LocalStack 4.9.2 S3 emulator
  `sha256:59373b4a27dba3ec15c4db0b7455f0cb68c8a42300e2cbbe362b440f9a131697`.

## Graphiti selection boundary

Pinned Graphiti `EntityEdge` publicly exposes `episodes`, `fact` and
`group_id`, but no exact source-start/source-end offsets. The fixed synthetic
fixture `Design approves sample.` fails candidate admission when a relation
claims the one-character-shifted span `[1,23)`. The same relation passes with
the exact `[0,22)` span. Oracle therefore uses Pydantic structured extraction
into `CandidateBundle` and a separate Falkor projection adapter; Graphiti
does not get confirmed-write credentials or direct admission authority.
Candidate invalidation cannot alter the confirmed store because the two
Falkor instances have distinct credentials and the extractor Postgres role
lacks accepted-ledger write permission. `GRAPHITI_TELEMETRY_ENABLED=false`
is set before importing the library. This follows the plan's bounded fallback
after the failing fixture, without forking Graphiti.

## Measured offline result

[CI run 36377021295](https://github.com/u2giants/theoracle/actions/runs/36377021295)
passed 20 Python contract/store checks on isolated Postgres, two authenticated
FalkorDB instances, and LocalStack S3. The same workflow validated S01 from
full Git history. Its sanitized artifact records the locked hash and outcomes.
The worker kill/replay test compared the same event ID and revision after a
real child process was terminated between graph write and receipt. Graph
candidate correction left confirmed state intact; the extractor DB role could
not write accepted rows, read checkpoint tables, or authenticate to the
confirmed graph. The projector also could not read checkpoint tables; a
third scoped checkpoint role serves the trusted conversation gateway.
The projector leases only allowlisted workspaces, and receipts bind and store
the projector identity and applied time; forged timestamps are denied.

On a GitHub Ubuntu 24.04 runner (4 CPUs, 16 GB RAM), the pilot loaded 10,000
nodes and 100,000 relations across three partitions with 20 concurrent
readers alongside a serial writer: p50 0.0578s, p95 0.2279s, zero forbidden
records. The separate 10x stress loaded 100,000 nodes and 1,000,000 relations:
p50 1.4765s, p95 2.1672s, zero forbidden records. The 2-second target applies
to pilot size. Both scales passed duplicate, historical correction, high-degree
node, source withdrawal, and partition-isolation probes. The confirmed
container's cgroup memory peak was 253,280,256 bytes against its 2 GiB limit.
The cgroup peak includes page cache and is an upper bound on resident memory.
Same-volume restart matched all counts in 7.203s; snapshot restore in a fresh
instance matched all counts in 3.161s.
The resource script, report JSON and Docker stats are in the CI artifact.

## Preview decision required

Two distinct Trigger.dev preview projects are proposed, one for the extractor
and one for the projector, both synthetic-only and separate from legacy
`proj_wgpzsvhmsopqhvwqaycn`. The extractor receives only candidate graph and
candidate Postgres credentials; the projector receives only confirmed graph,
projector Postgres and projection-signing credentials. Neither receives the
legacy Supabase service-role key. The technical reviewer must approve exact
project creation and deployment boundaries before provisioning. These preview
projects run no FalkorDB server (only the MIT client, pointed at an unreachable
host), so the FalkorDB SSPL deployment-fit verdict is required before any
FalkorDB server is hosted (S03), not before this preview; the qwen plan review
of 2026-09-28 gave an advisory internal-use opinion recorded in #26. The Python extension cold-start, clean exit and cancel
behavior must then be measured on those preview hosts. Trigger's extension
injects project environment variables into scripts, so the shared legacy
project cannot host these roles safely. No preview resource was provisioned.

The SQL in `services/oracle-brain/sql/001_foundation.sql` applies only to the
isolated local/CI database. Oracle's Supabase target remains unclassified for
this replacement; no production or preview schema migration was applied.

Sources: [Graphiti v0.30.2](https://github.com/getzep/graphiti/tree/v0.30.2),
[Trigger Python extension](https://trigger.dev/docs/config/extensions/pythonExtension),
[FalkorDB durability](https://docs.falkordb.com/operations/durability/persistence),
[uv CPU index guidance](https://docs.astral.sh/uv/guides/integration/pytorch/).

## Preview result (2026-09-28, dispatch revision 3, commit d879495)

Approved by qwen plan review (`VERDICT APPROVE`); approval record on #26.

| Field | Value |
|---|---|
| Extractor project | `dedicated-oracle2-extractor-preview`, `proj_esmuwkezljvasptkbiwr` |
| Projector project | `dedicated-oracle2-projector-preview`, `proj_jtaztxnmppzfchdsgvea` |
| Staging env vars | Set per dispatch step 2 (synthetic, 7 and 8 values) |
| Extractor deploy | Version 20260928.1, **failed** at image build after 81 s |
| Failure | Base image `triggerdotdev/node:24-bookworm`; the extension installs Debian `python3` = **3.11**. The bundle requires Python >=3.12, so pip found no 3.11 wheel for `lxml` and a source build failed (missing libxml2/libxslt headers). |
| Projector deploy | Not attempted (stop rule; identical Python bundle) |
| Runs, cold start, cancel, pause/resume | Not measured; no deployed version |

Outcome: the dispatch stop rule tripped. The Trigger Python extension host with
the pinned bundle **fails** S02's preview qualification as-is. The plan's
fallback (qualified container host with Python 3.12, separately reviewed) or a
separately reviewed change that supplies Python 3.12 on the Trigger image is
the next decision; no retry with changed pins was made under this approval.
Pause/resume was never part of the approved measurement set and remains open.
