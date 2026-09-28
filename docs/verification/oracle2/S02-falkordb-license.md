# S02 FalkorDB deployment-license fit — input for technical reviewer verdict

The plan (S02 selection rule) assigns FalkorDB license/deployment fit to the
designated technical reviewer. This file states the exact deployment the verdict
covers. It is a technical fit judgment, not legal advice.

## Components and licenses

| Component | Version | License | How Oracle uses it |
|---|---|---|---|
| FalkorDB server | v4.20.7, image digest pinned in `dev/oracle2/compose.yaml` | SSPL v1 (server `LICENSE`) | Unmodified container image as a private datastore |
| `falkordb` Python client | locked in `services/oracle-brain/uv.lock` | MIT | Oracle 2 workers connect to the server |
| Graphiti | v0.30.2 | Apache-2.0 | Candidate extraction library |

## Exact deployment covered

- Unmodified upstream FalkorDB server image, pinned by digest, no patches or forks.
- Two instances (candidate, confirmed), each password-protected, reachable only
  from Oracle 2 workers on a private network; never exposed to the internet or
  to any third party.
- Operated by POP Creations / Spruce Line for its own employees' internal use.
  Oracle's users interact with Oracle's own application (cited answers,
  corrections, recommendations); no user can issue graph queries or otherwise
  access FalkorDB functionality directly.
- FalkorDB is not sold, hosted for, resold, or offered as a service to any
  customer or outside party, and Oracle is not distributed outside the company.

## Question

Is FalkorDB (SSPL) fit for exactly this deployment? The verdict applies to this
version and these conditions only. Any fork/patch, external exposure, offering
to third parties, distribution, or version change needs re-review. Hosting
provider selection (S03) must preserve every condition above.

## Verdict

Designated technical reviewer (grok plan review, 2026-09-28, record
`grok-plan-review-20260928T145830-669726-17831.md`, `VERDICT APPROVE`):
technical fit **passes** for exactly this deployment of v4.20.7. Not legal
advice. Re-review on any fork, exposure, third-party offering, distribution,
version change, or S03 hosting choice that breaks a condition above.
