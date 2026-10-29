# Real-sample trial before step 8 (drift checkpoint follow-up)

Run 2026-10-29 ~2:40 AM EDT by MiMo on edge-dev, in response to the step-6
drift note on issue #240 ("before step 8 lands, run steps 2–6 on a small real
sample ... and record canonical-node counts and a hand-checked sample of
merges/false merges"). Pipeline: current `main` plus the step-7 branch (read →
flat → relations → resolve → project), real ScaleDown + OpenRouter calls,
ScaleDown path enabled. Writes only the shared test database; the corpus was
read from the `company_documents` bucket of the current Supabase project
(theoracle), which still holds the Oracle 1 uploads.

## Sample (4 real documents, 28 chunks)

| Source | Kind | Chunks | Mentions | Relations |
|---|---|---|---|---|
| Licensed_Team_Responsibilities_2_-_tagged.txt | text | 11 | 377 | 75 |
| Licensing_Sheet_Automation_Workflow.pdf | pdf | 8 | 173 | 98 |
| Pop_Creations_Flow_12112025__1_.png | image | 2 | 115 | 22 |
| SOP_Mockup_Creation.pdf | pdf | 7 | 54 | 12 |

## Canonical-node counts

- Mentions: 719 resolved / 0 unresolved (alias 171, embedding 179, judge 9,
  new 360; 49 judge calls).
- Entities: **360 canonical nodes, 12 joined across ≥2 sources.**
- Projected graph: **360 nodes, 172 edges.**
- Cost: 9 vision calls (14,011 tokens), 4 embedding batches (7,843 tokens),
  120 frontier calls / 101,681 frontier tokens (resolve incl. 71 descriptions).

## Hand-checked merges (the 12 multi-source entities)

Genuine cross-source joins — the failure mode of the old system is visibly
fixed at small scale:

1. `[Licensor] Disney` (7 mentions / 2 sources) — the responsibilities doc and
   the flowchart text both name Disney. Correct.
2. `[Person] Carlos` (3 / 2) — "Requests SKU#s and Clickup Cards from Carlos"
   joins the flowchart's team line to the responsibilities text. Correct.
3. `[Person] Albert (Buyer)` (3 / 2) — "Albert :)" (flowchart) and "Albert"
   (sample-shipping instruction). Correct.
4. `[Artifact] Tech Pack` (6 / 2) — tech pack / tech packs / techpacks across
   two documents. Correct.
5. `[Licensor] Licensor` (7 / 2), `[Vendor] Factories` (4 / 2),
   `[Product] Packaging` (2 / 2) — generic role/vendor terms merge cleanly.

Noisy or wrong (expected; the eval harness and the entity page exist for
this):

6. `[Role] Technical Designer` (9 / 3) — merges "Technical Designer(s)" with
   **"Creative designers"**, which the flowchart lists as a separate role.
   **False merge (over-merge).**
7. `[Process] Techpack Automation` (5 / 2) — merges distinct workflow stages
   ("Factory Production", "Licensing Review", "Technical Review") into one
   Process. **False merge (over-merge).**
8. `[Artifact] SKU_MOCKUP.png` (15 / 2) — the file-naming pattern
   ("SKU_MOCKUP.psd or .ai") is merged with instance mockup names
   ("VKP83DYMM02_MOCKUP.png"). Borderline: one mockup-artifact family, but
   the pattern and the instances are conflated.
9. `[Artifact] Packaging` and `[Product] Packaging` — the same surface lands
   as two entities of different types (extraction typed some mentions
   Artifact, some Product). Split, not merged.

## What this means before step 8

- Resolution quality is good enough for community detection to find real
  areas (licensing, tech packs, production standards) — the joins that the
  old claim store never made are happening.
- Over-merges cluster around generic nouns and adjacent workflow stages;
  communities will inherit them. Mitigation already planned: the entity page
  shows aliases (step 10), the eval harness measures merge precision
  (step 11), and the judge thresholds are env-tunable (plan §8).
- No blocker for step 8.

Posted by MiMo chat unknown on edge-dev
