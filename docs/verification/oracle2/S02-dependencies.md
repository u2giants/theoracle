# S02 dependency and runtime qualification

Status: implementation in progress. This is a synthetic foundation record,
not a business-quality or preview acceptance claim.

## Reproducible bundle

- Python 3.12.14; uv 0.12.19; `uv.lock` SHA-256
  `2c221d882eba1d52cb7a5d088a6647882f6c4054ec5c8ecaecf5346cf54dfbff`.
- Exported, hash-pinned `requirements.txt` SHA-256
  `162170d9b5115454c4fc5a0ec9c2b78f8016ab5e69391b5079db7257a8c45fe4`.
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

## Evidence still required

The CI-host real-store tests, crash/replay run, 10,000/100,000 graph resource
experiment plus 10x stress, and isolated Trigger preview cold-start/exit/cancel
have not passed as of this file version. Preview needs two distinct Trigger
projects or an independently reviewed bounded container host because the
Python extension injects project environment variables into scripts. The
legacy project has secrets and cannot safely host both roles.

Sources: [Graphiti v0.30.2](https://github.com/getzep/graphiti/tree/v0.30.2),
[Trigger Python extension](https://trigger.dev/docs/config/extensions/pythonExtension),
[FalkorDB durability](https://docs.falkordb.com/operations/durability/persistence),
[uv CPU index guidance](https://docs.astral.sh/uv/guides/integration/pytorch/).
