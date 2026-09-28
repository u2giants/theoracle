# S02 dependency and runtime qualification

Status: accepted on synthetic evidence, 2026-09-28 EDT. Offline qualification
first passed at `3b94d22` and is re-run by CI on every PR #45 head (the final
head's run is linked from the plan STATUS row); preview qualification passed on
Trigger staging (see "Preview result — revision 6"). This is not a
business-quality claim.

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

## Preview decision (resolved)

Two distinct synthetic-only Trigger.dev projects, one for the extractor and one
for the projector, separate from legacy `proj_wgpzsvhmsopqhvwqaycn`, because
Trigger injects project environment variables into scripts and the shared
legacy project cannot host these roles safely. The extractor receives only
candidate credentials; the projector only confirmed, projector and signing
credentials; neither receives the legacy Supabase service-role key. The exact
dispatch (`S02-preview-dispatch.md`) was independently approved before each
execution (records on #26), and the projects were provisioned and measured as
recorded below. They run no FalkorDB server; the SSPL deployment-fit verdict is
in `S02-falkordb-license.md`.

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

Outcome of revision 3: stop rule tripped (Python 3.11). Revision 4 (build
20260928.2) installed CPython 3.12.14 then failed uv first-index resolution;
revision 5 (build 20260928.3) installed 140 hash-checked packages and passed the
interpreter assertion, then failed in-container indexing on the config guard's
project-ref variables; revision 6 added those two non-secret variables. Each
revision was independently approved before execution (records on #26).

## Preview result — revision 6 (2026-09-28, 11:27 AM–11:31 AM EDT)

| Field | Value |
|---|---|
| Deployed commit | `6ccfe11` code (revision 6 changed only staging variables; dispatch doc at `1c02c0f`) |
| Extractor deploy | Version 20260928.4, build+deploy 97 s, CPython 3.12.14, 140 packages |
| Projector deploy | Version 20260928.1, build+deploy 102 s, CPython 3.12.14, 140 packages |
| Image size | Not reported by the Trigger CLI for remote builds; layer push 6.5–6.9 s |

| Run | Task | Result | Attempts | Queue→attempt start | Execution |
|---|---|---|---|---|---|
| `run_06geh8qadmd0mesi3ekuct6101` (a1) | synthetic run | COMPLETED, output `{"run_id": "…a1", "status": "accepted_synthetic"}` | 1 | 16.2 s (cold start) | 1.7 s |
| `run_06geh8qbqnskftmmfdp0ba1b01` (a2) | synthetic run, delayed 10 m | CANCELED while delayed | 0 | — | — |
| `run_06geh8rob937c1fsua0a31i101` (a3) | synthetic run | CANCELED immediately after trigger | 0 | — | — |
| `run_06geh8qcqh243oa71gj21avv01` (a4) | pause/resume | COMPLETED; `before` = `after` = extractor output; 30.6 s wall time including the 10 s wait | 1 | 15.4 s | 13.6 s |
| `run_06geh8qe655hn1i1fd6oc37901` | projector | FAILED closed, exit 1, stderr `{"status": "failed", "error": "OperationalError"}`; no URL or secret | 1 | 50.7 s | 4.2 s |

Findings: the Trigger Python host qualifies for S02 with the custom Python 3.12
layer: build, cold start, clean exit, cancellation (delayed and immediate) and
checkpoint/resume around Python steps all behave as specified, with one attempt
per trigger. Pause/resume proves platform checkpointing around Python
subprocesses, not Python-side state continuity. The projector's credential
boundary holds and it fails closed at the unreachable store; its successful
projection against a live store stays proven in CI. Runs cost $0.0001 each.
FalkorDB SSPL fit for internal use: see `S02-falkordb-license.md` (grok APPROVE);
models: see `S02-models.md` (grok APPROVE). Both preview projects are deleted
after #26 closes.
