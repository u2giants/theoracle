---
summary: "Audit of the brain against the owner's goals on 2026-11-11: graded verdict per goal and the numbered defects the repair plan fixes."
kind: proof
status: done
read-when: working a repair-plan step and needing the evidence behind a defect
---

# Oracle audit against the owner's goals — 2026-11-11

Written 2026-11-11, 7:45 AM EST, by Claude (Fable 5.2) for Albert Hazan.
Scope: `apps/brain/brain` (the Company Map service), the Teams bot route, and the live `cmap` data (read-only).
Method: four independent code reads, then spot-checks of the most serious findings against the code and the live database. Items marked *(inferred)* were read from code but not reproduced.

## Verdict

**Not perfect, and not yet trustworthy.** The skeleton for every goal exists and the engineering hygiene is good (every fact keeps a verbatim quote and a source). But the Oracle's own self-test scores **0.38 out of 1** against a target of 0.6 (run of 2026-11-10, 15 questions), and three of the seven goals are met only on paper.

| Goal | Grade | One-line reason |
|---|---|---|
| Learn from documentation | Partial | Reads most formats, but loses content silently and has no notion of old vs. new |
| Learn from interviews | Partial | Answers do become knowledge, but interviews are single questions, and the bot is switched off |
| Know what / whom to ask | Weak | Questions are whatever the model happens to suggest; no systematic gap finding |
| Segment into data domains | **Not met** | Domains exist but are not used when answering |
| Relationships between processes | Partial | Good relationship vocabulary; only finds links inside one paragraph |
| Big picture | Weak, with a live bug | Company-wide answers read every past version of every summary |
| Omniscient consultant extras | Weak | No live business numbers, no memory, corrections do nothing |

## Live state (read 2026-11-11, 7:36 AM EST)

- 57 sources: 12 documents (5 PDF, 5 text, 2 images) and 45 transcripts. The plan's target is hundreds of documents.
- 2,070 things known; **1,790 (86%) appear in only one source** — the joining across sources that the whole design depends on has barely happened yet, mostly because the corpus is small.
- 2,311 relationships.
- Questions: 67 open, 25 asked, 20 answered, **10,074 dismissed**. Interview bot is **off**.
- No source has an effective date.
- Self-test history: 0.20 (Nov 2), 0.20 (Nov 5), 0.47 (Nov 10, 5 questions), 0.38 (Nov 10, 15 questions).

## Confirmed defects, most damaging first

### 1. Company-wide answers read stale summaries (live, confirmed)
`answer/answer.py:725-731` loads every area and company summary ever written, with no version filter; summaries are never deleted (`graph/communities.py`, insert only). Live: **1,178 area summaries and 23 company summaries are stored; the current map has 32 and 1.** Every "big picture" question is answered from 35 generations of summaries mixed together, including ones describing merged-away or deleted material. The map pages and recommendations filter correctly; answering does not. Small fix, large effect — likely a real part of the 0.38 score.

### 2. Data domains are not used when answering (goal not met)
A specific question takes the 8 nearest things by similarity with no floor (`answer.py:410-416`), expands two hops ranked by company-wide popularity rather than relevance (`:447-451`), then adds 10 passages from the whole corpus (`:537-545`). Nothing keeps another department's material out; heavily mentioned hubs (a shared system, the owner) drag neighbours in. Each thing belongs to exactly one cluster (`communities.py:183-185`), clusters are mathematical groupings rather than business functions, they get new identities and names whenever one member changes, and the department label stored on each source is never used anywhere.

### 3. No sense of time, versions, or contradiction
A revised procedure is a second source; both versions stand with equal weight. The effective date is stored and never used (confirmed: only the upload API touches it). Contradictions are only noticed inside a single paragraph (`extract/relations.py:74`). An interview answer that contradicts a document triggers nothing.

### 4. Relationships are found only inside one ~400-word passage
Both ends and the quote must sit in the same passage (`extract/relations.py:247-250`). PDF passages never cross a page; transcript passages break at every speaker change. "Who approves it?" / "Jessica does" across two turns yields nothing. Cross-department hand-offs — the edges between clusters — are also excluded from every summary (`communities.py:489-491`). There is no step order, so an end-to-end flow such as order-to-cash cannot be laid out in sequence; sequence links stated once lose to frequently repeated generic mentions when lists are trimmed.

### 5. Silent loss while reading
- One bad model reply discards a whole source's extraction while the source still shows as read; failed jobs are never retried (`extract/flat.py:435-451, 650-655`; `worker.py:87-99`, confirmed). 7 failed jobs are sitting in the live queue.
- The passage splitter drops text: 2,022 Chinese characters in, 1,083 out; 18 of 400 spreadsheet rows appeared whole in no passage (`read/chunk.py:60-70`, demonstrated by running it).
- Word/PowerPoint/Excel files with a hyperlink or embedded chart are rejected outright (`read/office.py:79-87`) *(inferred, not run on a real file)*.
- Spreadsheets lose column alignment and headers; diagrams on PDF pages that also carry text are ignored (`read/pdf.py:54`).

### 6. No systematic gap finding
The only source of interview questions is up to three free-form suggestions the model makes while writing an area summary (`communities.py:766`). Nothing checks for processes with no owner, steps that lead nowhere, things mentioned once, thinly covered departments, or contradictions. The 10,074 dismissed questions show how noisy that source has been.

### 7. Interviews are single questions, and replies can misfile
- Any reply judged even partly an answer closes the question; no probing of a vague answer, no check that the gap was filled (`interview/inbound.py:344-349`).
- "I don't know, ask Maria" — the referral is thrown away (`inbound.py:318-331`).
- An ignored question is never re-asked or re-routed.
- A late reply to question one can be saved as the answer to question two (3-day vs 7-day windows, `tick.py:48,235` vs `inbound.py:33,303`).
- A question can be posted into a group or meeting chat if that is where the person last wrote to the bot (`inbound.py:237-238`) *(inferred)*.
- Only people who have already described their own department are routable; no structured "tell me about your job" interview for a role or a new hire.

### 8. Wrong and duplicate identities are permanent
A lone first name is attached to the only person whose name starts with it, and stays attached when a second person with that name appears (`resolve/resolve.py:640-651`). Duplicates are never merged after the fact. Generic step names ("review") merge company-wide.

### 9. "Mark wrong" changes nothing
Review flags are stored and can be resolved, but no reading, answering or recommending code ever looks at them (confirmed by search). There is no merge, split or rename. A flagged error is repeated before and after every rebuild.

### 10. Citations prove a source exists, not that it supports the sentence
For company-wide answers any valid source is accepted, even one the model was never shown (`answer.py:333-359`). Sentences with no citation at all are passed through unmarked (`answer.py:276-278`), contrary to the file's own description.

### 11. Consultant layer is thin
- Documents and conversations only: no orders, sales, lead times or KPIs. Recommendations therefore cannot be sized.
- Recommendations are one-off cards with a status; no owner, no result, no follow-up measurement.
- The Teams bot cannot be asked a question — answering exists only on the web page.
- Web chat remembers six turns in the browser only; questions employees ask are not logged or learned from.
- Nothing in the release checks stops a change that halves answer quality from shipping; the automated test replays recorded answers.
- One worker, no retry or backup model provider.

## What is solid

- Every fact and relationship carries an exact quote and a locator; fabricated quotes are dropped.
- Policy / practice / report / inference is tracked on every relationship.
- Interview answers flow through the same pipeline, attributed to the speaker.
- Pacing guards on interviews: weekly cap, quiet hours, kill switch, vetting before sending.
- Recommendation guardrails: invented numbers are scrubbed, "do nothing" is always an option, rejected ideas are not re-proposed.
- The graph can always be rebuilt from the database; deploy restarts no longer orphan work.
- Chinese reading, asking and answering are in place.

## What an omniscient consultant still needs (beyond the fixes above)

1. Live operational numbers (orders, lead times, late shipments, chargebacks) so a problem can be sized and a fix measured.
2. A curated list of business functions (Licensing, Sourcing, Design, Sales, Logistics, Finance…) that clusters are pinned to, with things allowed in more than one.
3. Ordered end-to-end flows with owners, inputs, outputs, triggers and approval points.
4. Computed bottlenecks and single points of failure (the person or system everything routes through).
5. A coverage scorecard per function: how much is known, how old, how many sources agree — which is also the question generator.
6. Time: newer supersedes older; "last confirmed" on every fact; periodic re-confirmation.
7. Corrections that stick.
8. A quality bar that blocks releases.

## Suggested order of repair

1. Stale-summary bug (item 1) and retry of failed reading (item 5, first bullet) — small, immediate quality gain.
2. Load the rest of the corpus — 12 documents cannot show the big picture.
3. Domain-aware answering with curated functions (item 2).
4. Dates and supersession (item 3).
5. Cross-passage relationships and ordered flows (item 4).
6. Systematic gap finder feeding real multi-turn interviews (items 6–7).
7. Corrections that stick (items 8–9).
8. Operational data.
