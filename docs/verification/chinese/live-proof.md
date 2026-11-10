# Chinese (Mandarin) integration — live proof (plan step 4.2)

Written 2026-11-10 by MiMo (ah-desktop session `ses_ffe5e3c778c43ffeJNqN2nnAd4`).
Plan: [plan_chinese_integration.md](../../plan_chinese_integration.md) — tracking issue: https://github.com/u2giants/theoracle/issues/474

Production state at proof time: web https://oracle.designflow.app (Vercel, auto-deployed
from main), brain https://oracle-brain.designflow.app on image
`ghcr.io/u2giants/theoracle-brain:c332f33e874eae56853a40640679b812a3e2f8a7`
(deploy `80nfbnup5yukcdaqjuco4gcq`, env pin PATCHed first per the stale-pin rule),
migrations `011`–`014` applied via `python -m brain.migrate` (run twice, exit 0).

All evidence below is real production output (brain API + production database
reads). Screenshots of the browser Map are covered by the e2e run
(`apps/web/tests/__screenshots__/map/12-zh-community.png`, `13-zh-entity.png`);
browser screenshots of the live site need a signed-in human session and are
listed under open items.

## 1. zh document ingested → Map shows Chinese names ✅

Ingested `docs/verification/chinese/fixtures/sample-zh-process.txt` (synthetic
采购审批 paragraph) plus the three fixture sources (Teams transcript, licensing
PDF, flowchart PNG) through `POST /sources` (the Map → Sources path). All four
sources reached `read_state: read`; extraction produced Chinese mentions with
verbatim Chinese quotes (`cmap.mention`, production):

| surface | type | quote (first 30 chars) |
|---|---|---|
| 采购审批流程 | Process | 采购审批流程由采购部发起：张三创建采购单后交给李四复核，李四确认供应商已在ERP… |
| 采购部 | Department | 同上（同句） |
| 张三 | Person | 同上（同句） |
| 采购单 | Artifact | 同上（同句） |
| 李四 | Person | 同上（同句） |
| ERP系统 | System | 同上（同句） |
| 王五 | Person | 同上（同句） |
| 付款环节 | Step | 终审通过后采购单进入付款环节； |
| 五万元 | Metric | 如果金额超过五万元，需要总经理额外批准。 |
| 总经理 | Role | 如果金额超过五万元，需要总经理额外批准。 |
| 供应商资料 | Artifact | 常见问题是供应商资料在ERP系统里缺失，导致复核退回。 |
| 复核退回 | Issue | 常见问题是供应商资料在ERP系统里缺失，导致复核退回。 |

Extraction models recorded on the chunk: `scaledown/classify`, `z-ai/glm-5.3-flash`.
Source ids: `9222dca2-daea-4765-994c-db711389d17e` (zh sample),
`15216474-479f-496e-a8be-e703875ecc4f` (transcript).

## 2. Chinese question → Chinese answer with verbatim quotes ✅

`POST /answer` with `{"question": "我们的跨境审批卡在哪里？", "mode": "auto"}` on
production returned (`mode_used: local`):

> 数据中没有记录显示跨境审批目前卡在哪一步，也没有给出“跨境审批”的定义，因此无法判断卡点。
> 能找到的相关内容如下： - **政策（海关商标授权）**：数据中有一段标为用于海关的商标授权流程，
> 其中要求由 Lic Manager 向各授权方申请商标授权表。 [1] [2]这是步骤清单，没有显示耗时或当前进度。
> - **政策（授权方PPS审批）**：PPS 照片由 Licensed Team 提交到授权方门户。 [3]
> - **政策（意见回传工厂）**：在把授权方意见发给工厂之前，团队需先核对问题是否出在美术文件或授权方资产上。 [4]
> - **同事提出的问题（未作答）**：有人问授权方通常需要多久评审概念，以及是否在门户中追踪这段时间，
> 但数据中没有对应答案。 [5]
>
> 如果你指的“跨境审批”是某一个具体环节（海关商标授权、工厂审核，还是授权方样品审批），
> 请告诉我，我可以基于数据继续查。

Citations (5) keep their quotes in the ORIGINAL language (never translated):

1. `1781724327149-Licensed_Team_Responsibilities_2_-_tagged.txt` — "Submit the Reports … ## Trademark Authorization (for Customs Purposes"
2. 同上 — "Request Trademark Authorization forms from Each Licensor"
3. 同上 — "Licensed Team submits the PPS photos in the Licensor Submission portal"
4. 同上 — "issue may be the art file or the licensor’s asset"
5. `Teams contribution — Laura Arevalo — 2026-11-04` — "How long does a licensor typically take to review your concepts"

The answer is in Chinese (the question's language), cites English evidence with
English quotes verbatim, distinguishes 政策 from one person's report, and
refuses to guess what the data does not say.

## 3. zh employee conversation lands as a Teams contribution source — pending

Needs the China-office employee Albert picks (see open items).

## 4. zh interview question delivered → answer becomes a source — pending

Same pick as item 3.

## 5. zh eval run — queued; calibration recorded

Ten zh draft questions (plan O4: 5 process, 3 cross-source, 2 negative) are
seeded and graded language-neutrally. The fixture-replay calibration run is
`25914471-8521-4d21-b465-d1540a154292` (mean 1.000 over all 15 questions).
The production `evaluate` job `c0a1b5f5-33a8-4848-9c6c-571bdc014b15` was
queued 2026-11-10 11:06 AM EST behind the fixture-corpus pipeline chain
(classify/extract/relations); its run id and mean append here when it lands.

## Open items (not yet proof)

- [ ] Item 3/4 + business acceptance: Albert picks the China-office employee
  (plan suggests Emma Li) for a 10-minute Chinese Map + chat pass; that person's
  bot conversation and one zh interview round complete items 3–4.
- [ ] Browser screenshots of the live site (needs a signed-in human session).
