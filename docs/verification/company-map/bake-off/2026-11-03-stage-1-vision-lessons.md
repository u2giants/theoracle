---
summary: "Lessons from the stage 1 vision bake-off of 2026-11-03: method, traps and what to change on a re-run."
kind: proof
status: done
read-when: re-running or questioning the diagram-reading model choice
---

# Stage 1 vision bake-off: what we learned (2026-11-03)

This is the companion to the
[stage 1 results](https://github.com/u2giants/theoracle/blob/main/docs/verification/company-map/bake-off/2026-11-03-stage-1-vision.md)
([JSON](https://github.com/u2giants/theoracle/blob/main/docs/verification/company-map/bake-off/2026-11-03-stage-1-vision.json)),
merged in u2giants/theoracle#330. The results file has the scores. This file covers
the findings, the method, the problems we hit and the open decisions, so the
coordinator and any later bake-off can reuse them without repeating the work.

## 1. Findings for the product

1. **The current vision model (`openai/gpt-4.1`) is not reading our real diagrams.**
   On the Edge Home "Licensed Flow" swimlane chart it returned 64 boxes but **zero
   arrows**. Only 40% of its box labels match the page, and 23 labels exist nowhere
   on it ("Meeting Assembly", "Jewelry versions", "Vetting + Buyer Introduction").
   The production graph built from that image so far is mostly invented. It still
   scores 100% on the small test fixture, which is why earlier checks never caught
   this.
   - Consequence: once the vision model changes, the flowchart source should be
     re-read and re-extracted. That re-ingest is the coordinator's or Albert's call.
     It is not done here.
2. **`anthropic/claude-haiku-5.5` is the clear pick.** It copied every box label and
   every lane exactly, got 95.5% of arrows (64/67) and 10/11 arrow conditions, and
   made 4 wrong arrows. It was the only model that reported clipped text honestly in
   `unreadable_regions`. It costs about $0.005 per dense diagram and about $0.0005
   per text-poor page.
3. **`openai/gpt-6-luna` is a credible runner-up** at the same price per token. It
   used about 2× the input tokens but fewer output tokens, so it was cheaper overall.
   At full size it missed 2 labels and 3 arrow conditions. On a downscaled copy it
   read every label.
4. **Fixture-only testing is not enough.** All six models scored 100% on the fixture
   flowchart and 100% on the plain-text SOP page. Only the large real swimlane chart
   separated them. Any future vision bake-off must include a dense real diagram.
5. **Image size is a hard limit for some providers.** `meta/muse-spark-1.3-contributor`
   returned HTTP 400 "image decode limit exceeded" for the 6359×7610 px original.
   Production sends originals unresized (`apps/brain/brain/read/vision.py` base64s
   the raw bytes), so in production that model would simply fail on this file.
   On a 2590×3100 copy it worked but found only 49% of arrows.
   - Side observation: downscaling to about 2600 px wide cost Haiku some arrow recall
     (0.955 → 0.881) but fixed Luna's missed labels. If a size cap is ever added to
     the reader, test it against this chart first.
6. **Typical failure shapes**, useful for judging other stages too:
   - Gemini 3.8 Flash reads every label but links boxes by position (row order)
     instead of following the drawn arrows: 16 wrong arrows. It also costs about 6×
     Haiku because its image input is billed at a higher rate.
   - Qwen 2.5 VL 72B misses most lane headers (4/14), makes 41 wrong arrows and is
     the slowest (69 s).
   - GPT-4.1 behaves like the "summarize instead of transcribe" pitfall in the job
     brief.
7. **JSON reliability is not a differentiator.** Every model returned parseable JSON
   under the production prompt with no JSON mode, except Muse's HTTP 400.

## 2. The test material (what exists and where)

- The real-corpus sources and their storage paths are listed in table `cmap.source`
  of the test database `cmap_bake_5` (read-only). It contains 1 image (the flowchart),
  4 SOP PDFs and 3 text files.
- Text-poor pages (under 200 native characters, which production routes to vision):
  `Licensing_Sheet_Automation_Workflow.pdf` pages 1–4 (page 2 has 1 character) and
  `SOP_Mockup_Creation.pdf` page 3 (100 characters). That makes 7 such pages across
  those two PDFs. The other two SOP PDFs were not fetched.
- The flowchart is 6359×7610 px, 1.18 MB, sha256 prefix `d087b916f5e1f73d`. It has
  14 lanes ("Albert :)", Buyer, Sales, Creative direction, Junior designer, Technical
  designers, Creative designers, Sourcing, Production, Carlos, Gina, Licensing Team,
  Licensor, Factories), 62 boxes and 12 arrow-condition labels.
- The hand-built reference (lanes, boxes, 67 certain arrows, 11 accepted-ambiguous
  arrows, the exact SOP page text) is stored under `reference` in the stage 1 JSON.
  Later sessions can rescore new candidates against it without rebuilding it.
  - Genuinely ambiguous parts of the drawing: the dashed fan-out from "Concept Submit
    to Licensor" to the three licensor-response boxes; the "Before an Order" line from
    "Factory selection", which passes through "Files for Factory" to "Sampling"; and a
    few overlapping connectors near Costing sheets, Include in Task List and Concept
    image to ColdLion. These are accepted but never required.

## 3. How to reproduce or extend

1. Fetch originals read-only from production storage, bucket `company_documents`,
   using the `storage_path` values in `cmap.source`. The Supabase MCP server failed
   to start in this session, so the fetch used the Supabase management API to get the
   service key at runtime, then a plain GET on `/storage/v1/object/company_documents/<path>`.
   - Credentials came only from 1Password through `op_run` environment references:
     the Supabase CLI personal access token item in `vibe_coding`, and the OpenRouter
     key item named in the common rules. No values were printed or stored.
2. Render PDF pages with `pdftoppm -r 150 -png` (poppler). ImageMagick is not
   installed on the test services host; use Pillow through
   `uv run --with pillow` for resizing.
3. Call each model with the real production prompt (`load_visual_prompt()`) and
   `brain.llm.post_chat_with_rescue` at temperature 0, one call per model per image,
   from `apps/brain` via `uv run`. Run models in parallel as detached processes
   (`setsid nohup … &`). A single foreground `op_run` that waits on all of them
   exceeded the MCP connection lifetime ("Connection closed") after the fast calls
   finished, so the slow flowchart calls were lost and rerun. Write each result to
   its own file and skip files that already exist, so reruns are cheap.
4. Score deterministically: fuzzy label match (normalized, ≥0.85 similarity), map
   each returned arrow's endpoints to reference boxes, then count recall and wrong
   arrows. Spot-check the wrong arrows of the top models by hand (done; they are
   real misreads, not matching errors). No LLM judge is needed for this stage.
5. Cost: use `usage.cost` from the OpenRouter response (actual billed), not
   list-price arithmetic. Image tokens are billed differently per provider, which
   is why Gemini's low reported input token count still cost the most.

## 4. Process problems hit (for the people running bake-offs)

- **The whole-repo `ai-doc-safety` check hung** for more than 10 minutes. It was
  stuck inside `ai-public-boundary-check`, on a `git grep -anE '([A-Za-z0-9-]+\.){2}ts\.net'`
  pass pegged at 99% CPU. I stopped it and applied the checker's own patterns to just
  the two changed files, which were clean. The tool itself was not repaired.
  It needs an owner (see open items).
- The Supabase MCP server and the recall-ai MCP server failed to start
  ("Executable not found in $PATH: cmd"). This looks like a Windows-style launcher
  config on a Linux host. It was worked around for reads, but not fixed.
- `op item list` output for the `vibe_coding` vault is about 136k characters. Filter
  it locally rather than reading it.
- Total OpenRouter spend for stage 1 was about $0.09 (21 calls). Limit remaining was
  $24.22 before the run, so the per-session $2.50 cap was never close.

## 5. Open items (not done in this session)

- **Coordinator:** fold the stage 1 winner into
  `docs/company-map/model-stage-job-brief.md` (§4.1 and the scoreboard row "1 Vision")
  and decide the production `BRAIN_VISION_MODEL` switch. This session was told not to
  edit the brief or production settings.
- **Coordinator or Albert:** after the switch, re-read and re-extract the Edge Home
  flowchart source, because its current graph comes from GPT-4.1's invented reading.
- **Tooling owner (ai-devops):** repair the `ai-public-boundary-check` `ts.net` grep
  hang, and fix the Supabase and recall-ai MCP launcher configs on the Linux host.
- **Optional:** a second dense real diagram would make the ranking sturdier. The
  corpus has only one, so the current ranking rests on a single image (plus a fixture
  and a text page where all models tied).
