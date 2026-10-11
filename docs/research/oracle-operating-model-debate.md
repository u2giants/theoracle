# Oracle operating-model replacement: evidence and Muse debate

Decision owner: implementation-plan author; runtime adoption owner: the session
claiming W01 on #27. Written October 11, 2026 EDT. This is a durable companion to
[the canonical plan](../../plan_oracle_workflow_integrity.md), not a second plan
or a runtime approval. Retain the decision reasoning here through plan execution;
W12 consolidates any enduring operating rules into the architecture topic.
All implementation rows remain open.

## User request and correction of the prior recommendation

Albert requested retaining FalkorDB and GraphRAG, fixing lost conflicts/missing
information, explicit PM4Py workflows and useful patterns from ProMoAI,
agency-agents, ODD and the CrewAI consultant. The published PR85 plan extended
the current extraction/runtime. When he asked whether that was code preservation,
Codex recommended a scoped clean knowledge-to-workflow replacement but admitted
the published plan did not require that boundary or rebuild. Albert then said:
“make the implementation plan the best possible plan. then have Muse critique it
(give it all the available data and background) and debate it out with Muse to
come up with the best plan.” That authorizes planning/debate/publication, not
application implementation, private-provider changes or paused company grading.

## Evidence supplied to Muse

Muse Spark 1.3 Contributor was given the disposable public repository packet,
its manifest, current plan, complete parent plan, research/acceptance/environment/
verification documents, current source and tests, historical macro-first/R2
diagnosis reading map, and public pinned recovery handoff plus full recovery
`graph/graphrag.py`, `graph/retrieval.py` and `holistic_runtime.py` contents.
The recovery reference is immutable
[36e91038](https://github.com/u2giants/theoracle/commit/36e91038ee6b1126f9d9c27adce7583a6b74c654);
main at first review was
[ead22733](https://github.com/u2giants/theoracle/commit/ead22733d0e4a72befd9b17e9d4976ba88e8e924).
Current #27 publication receipts were read by Codex; their sanitized delivery
status is in the brief. The first critique could inspect source but could not
execute SDK tests: its disposable copy had no installed SDK or ignored .venv.
No runtime verification is inferred from the critique.

Private-original contents, credentials, unredacted raw model outputs and private
answer keys were not supplied. The existing processing register does not admit
private company originals to Muse. Sanitized historical corpus/audit state was
included: eight distinct originals/26 aliases; reported 94 local synthetic
checks; two originals essential-audited, three detail ambiguity findings, third
audit truncated, five unaudited and 28-category cross-document audit unrun.
These counts are historical engineering receipts, never company acceptance.
Closed credential incident, $25/day limit, paused company questions/Ilona/Jessica
grading/employee messages, independent hosting authority blocker and fixed-port
runner collision were all included. Existing private stores were untouched.

Primary source snapshots refreshed October 11, 2026 EDT; source inspection is
not installation, license fit or dependency qualification:

| Repository | Immutable snapshot | Source supplied |
|---|---|---|
| [process-intelligence-solutions/pm4py](https://github.com/process-intelligence-solutions/pm4py/tree/2a245b9a5e7701edb2bc745bbfcb0a441d2b39ab) | `2a245b9a5e7701edb2bc745bbfcb0a441d2b39ab` | README.md |
| [fit-process-mining/ProMoAI](https://github.com/fit-process-mining/ProMoAI/tree/af9b95b73e33fd21f4a4d158252094f192440c42) | `af9b95b73e33fd21f4a4d158252094f192440c42` | README.md |
| [msitarzewski/agency-agents](https://github.com/msitarzewski/agency-agents/tree/f99f6aa910a442b0197b768ce0ea7751e35e2060) | `f99f6aa910a442b0197b768ce0ea7751e35e2060` | README.md |
| [opendatadiscovery/odd-platform](https://github.com/opendatadiscovery/odd-platform/tree/015f6fa2dac9b6d0dfd00b6b6d9baab9329e6c4f) | `015f6fa2dac9b6d0dfd00b6b6d9baab9329e6c4f` | README.md |
| [hanantabak2/crewai_ai_business_consultant_on_streamlit](https://github.com/hanantabak2/crewai_ai_business_consultant_on_streamlit/tree/d26810edf0c2713726ef0c2c9864a7f989b67c39) | `d26810edf0c2713726ef0c2c9864a7f989b67c39` | README.md |

The full current upstream READMEs accompany the second Muse brief as public
background; the plan’s selected API links and historical PM4Py pin remain
qualification references. No copied upstream runtime code is delivered.

## Round 1: adversarial critique of both patching and rebuild

Muse returned REVISE. It independently found the dropped string arrays in main
and the difference between main and unmerged recovery occurrence/retrieval fixes.
Main endpoint-loss risk is inferred from missing recovery mechanisms plus the
recovery’s real-store regression; Muse did not run the SDK in its copy. It
rejected an unbounded wipe and supported a scoped clean core, subject to explicit
keep/replace/retire evidence.

| Objection | Codex disposition / change |
|---|---|
| B1 code-preservation trap | Adopted: §8.0 and W01 require precise boundary review, new operating_model core, allowed helper inventory and import tests; W02/W05/W06 no longer extend old core |
| B2 no company operating-model artifact | Adopted: §8.2a and W03 define process/role/artifact/interface/variant/findings model with independent census; W06 exposes company overview |
| B3 main/recovery mismatch | Adopted invariant regressions; disagreed that whole recovery must merge first. New core builds on current main independently, transfers only reviewed mechanisms, preserves privately owned state |
| H1 legacy strings can become facts | Quarantine adopted. Disagreed with erasing visibility entirely: authorized review pane preserves unverified findings; answers/recommendations cannot use them as factual evidence |
| H2 PM4Py before license admission | Adopted qualification-first W04a and admitted pinned W04b; no dependency/bundle promotion before exact fit. Process isolation is not a license workaround |
| H3 unmeasurable census/one monolithic gate | Adopted source-only independently frozen inventories, explicit essential/detail rules, one affected retry and finite cost reservations; separate mechanical/diagnostic/semantic acceptance |
| H4 model self-review/receipt inflation | Adopted independent semantic acceptance requirement; same-model critique is diagnostic only; private admission and paused grading remain binding |
| H5 scope and optional later slices | First documentary slice adopted. Disagreed that requested PM4Py/import/consulting could simply become optional or Done with no export. Synthetic engineering remains required, actual-data acceptance stays open |
| M1–M4 revision/aliases/seals/retirement | Adopted authoritative integer revision, earliest alias test, payload seals, bounded comparison and reversible manifest cutover; no whole-app wipe |

## Debate status

Round 2 is requested against the revised source and these explicit disagreements.
No consensus or final review approval is claimed yet. Final decisions and exact
review identity will be recorded here and on #27 after the debate completes.

## Current selected architecture

One new Python operating-model core; one durable evidence/artifact authority;
real FalkorDB/GraphRAG adapters; explicit source-local observations and findings;
cross-source company assembly; separate per-process workflows; bounded verified
evidence packs. Retain source custody/identity/admission/authentication/transport
only with invariant tests. Preserve unresolved information visibly without
promoting it to truth. No arbitrary agent code executor, competing memory owner
or five new platforms. Formal and observed analyses remain distinct.

Posted by Codex chat 01a12b2c-9fa9-72c0-a132-341a402873d8 on edge-dev3
