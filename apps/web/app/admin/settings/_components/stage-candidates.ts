// Top three models per Company Map stage from the 2026-11-03 bake-off
// (docs/verification/company-map/bake-off/2026-11-03-stage-*.md). Scores are
// each stage's quality (0–1) against its judged reference; the page shows them
// relative to the stage's best. Prices are OpenRouter list prices per million
// tokens, read from https://openrouter.ai/api/v1/models on 2026-11-03.
// `recommended` marks the bake-off winner, which weighs cost and failures as
// well as quality, so it is not always the highest score.

import type { StageId } from './stage-briefs';

export const PRICES_AS_OF = '2026-11-03';

export interface StageCandidate {
  model: string;
  quality: number;
  /** USD per 1M input tokens. */
  priceIn: number;
  /** USD per 1M output tokens; null for embeddings (input only). */
  priceOut: number | null;
  recommended?: boolean;
  good: string;
  weak: string;
  vsBest: string;
}

export const STAGE_CANDIDATES: Record<StageId, StageCandidate[]> = {
  vision: [
    {
      model: 'anthropic/claude-haiku-5.5',
      quality: 0.94,
      priceIn: 0.1,
      priceOut: 0.5,
      recommended: true,
      good: 'Most accurate arrows and lanes on the real flowchart (64 of 67 links right) and the only model that flagged labels it could not read.',
      weak: 'Got 4 links wrong.',
      vsBest: 'Top scorer.',
    },
    {
      model: 'openai/gpt-6-luna',
      quality: 0.876,
      priceIn: 0.1,
      priceOut: 0.5,
      good: 'Cheapest per flowchart; read every box correctly on a smaller copy.',
      weak: 'Missed 2 box labels and 3 arrow conditions on the full-size flowchart.',
      vsBest: 'Close second: slightly less complete than Haiku, a little cheaper.',
    },
    {
      model: 'google/gemini-3.8-flash',
      quality: 0.824,
      priceIn: 0.825,
      priceOut: 4.125,
      good: 'Read every label and lane perfectly.',
      weak: 'Linked boxes by position instead of following arrows (16 wrong links); most expensive.',
      vsBest: 'Better at labels, much worse at how steps connect, about 7× the cost.',
    },
  ],
  embed: [
    {
      model: 'voyageai/voyage-4-lite',
      quality: 0.888,
      priceIn: 0.02,
      priceOut: null,
      recommended: true,
      good: 'Best at telling different things apart, so fewer wrong merges of names; about 6× cheaper than the current model.',
      weak: 'Slightly weaker at putting the best passage first in search.',
      vsBest: 'Top scorer.',
    },
    {
      model: 'openai/text-embedding-3-large',
      quality: 0.877,
      priceIn: 0.13,
      priceOut: null,
      good: 'Best at ranking the right passage first in search.',
      weak: 'Rarely scores true name variants high enough to merge them automatically.',
      vsBest: 'Nearly tied; better search ranking, weaker name matching, about 6× the cost.',
    },
    {
      model: 'openai/text-embedding-3-small',
      quality: 0.835,
      priceIn: 0.02,
      priceOut: null,
      good: 'Same low price as Voyage.',
      weak: 'Clearly weaker search: finds the right passage in the top 5 only 83% of the time.',
      vsBest: 'Same cost, noticeably worse search.',
    },
  ],
  flat: [
    {
      model: 'deepseek/deepseek-v4.1-flash',
      quality: 0.752,
      priceIn: 0.045,
      priceOut: 0.5,
      good: 'Found the most items and never skipped a useful passage.',
      weak: 'Thinks at great length: about 12× the cost of GLM and around 2 minutes per passage.',
      vsBest: 'Top scorer by a hair over GLM, at about 12× the cost.',
    },
    {
      model: 'z-ai/glm-5.3-flash',
      quality: 0.748,
      priceIn: 0.0313,
      priceOut: 0.0846,
      recommended: true,
      good: 'Essentially tied for best, far cheaper and faster than the others.',
      weak: 'Wrongly skipped 1 of 25 passages as small talk.',
      vsBest: 'Practically the same quality as DeepSeek for about a twelfth of the cost.',
    },
    {
      model: 'qwen/qwen3.8-27b',
      quality: 0.729,
      priceIn: 0.15,
      priceOut: 1.875,
      good: 'Finds a lot of items.',
      weak: 'Many of them are wrong; slowest and by far the most expensive.',
      vsBest: 'Less accurate than DeepSeek and roughly 4× its cost.',
    },
  ],
  relations: [
    {
      model: 'z-ai/glm-5.3',
      quality: 0.626,
      priceIn: 0.08,
      priceOut: 3.6,
      good: 'Most correct links found, with no failures.',
      weak: 'About 5× the cost of Muse.',
      vsBest: 'Top scorer, tied with Muse within testing noise.',
    },
    {
      model: 'meta/muse-spark-1.3-contributor',
      quality: 0.625,
      priceIn: 0.1,
      priceOut: 0.2,
      recommended: true,
      good: 'Tied for best, no failures, the widest range of link types (hand-offs, exceptions) and the cheapest of the top models.',
      weak: 'Slow: about 38 seconds per passage.',
      vsBest: 'Same quality as GLM-5.3 for about a fifth of the cost.',
    },
    {
      model: 'anthropic/claude-haiku-5.5',
      quality: 0.592,
      priceIn: 0.1,
      priceOut: 0.5,
      good: 'Accurate links when it finishes.',
      weak: 'Ran out of room on 56% of passages, losing the last links in each.',
      vsBest: 'Somewhat lower and unreliable on long passages.',
    },
  ],
  resolve: [
    {
      model: 'openai/gpt-6-luna',
      quality: 0.87,
      priceIn: 0.1,
      priceOut: 0.5,
      recommended: true,
      good: 'Best written descriptions, cheapest, no failures.',
      weak: 'Slightly more wrong merges than Muse.',
      vsBest: 'Top scorer.',
    },
    {
      model: 'meta/muse-spark-1.3-contributor',
      quality: 0.85,
      priceIn: 0.1,
      priceOut: 0.2,
      good: 'Fewest wrong merges (1 in 13).',
      weak: 'Very wordy, slowest, weaker descriptions.',
      vsBest: 'Safer at merging, worse at describing, about twice the cost.',
    },
    {
      model: 'deepseek/deepseek-v4.1-flash',
      quality: 0.82,
      priceIn: 0.045,
      priceOut: 0.5,
      good: 'Good merge decisions.',
      weak: '3 empty replies needed a retry; most expensive because of long thinking.',
      vsBest: 'Lower quality and about 3× the cost.',
    },
  ],
  reports: [
    {
      model: 'openai/gpt-6-luna',
      quality: 0.816,
      priceIn: 0.1,
      priceOut: 0.5,
      recommended: true,
      good: 'Most accurate and easiest to read, among the fewest unsupported claims, fast.',
      weak: 'The long company-wide report was cut off once at the length limit.',
      vsBest: 'Top scorer.',
    },
    {
      model: 'anthropic/claude-haiku-5.5',
      quality: 0.789,
      priceIn: 0.1,
      priceOut: 0.5,
      good: 'Good, readable reports.',
      weak: '3 of 12 reports were cut off at the length limit; costs about 70% more.',
      vsBest: 'A little lower, less reliable, more expensive.',
    },
    {
      model: 'z-ai/glm-5.3-flash',
      quality: 0.765,
      priceIn: 0.0313,
      priceOut: 0.0846,
      good: 'Cheapest; every report came back complete.',
      weak: 'More unsupported claims than Luna.',
      vsBest: 'Lower accuracy, about 40% cheaper.',
    },
  ],
  answer: [
    {
      model: 'z-ai/glm-5.3-flash',
      quality: 0.682,
      priceIn: 0.0313,
      priceOut: 0.0846,
      good: 'Top average by a hair, about 4.5× cheaper than Haiku, faster.',
      weak: 'Every first attempt came back empty; only the automatic retry produced answers. Lower correctness.',
      vsBest: 'Top scorer, but tied with Haiku within testing noise.',
    },
    {
      model: 'anthropic/claude-haiku-5.5',
      quality: 0.68,
      priceIn: 0.1,
      priceOut: 0.5,
      recommended: true,
      good: 'Most honest about what the documents do not say; reliable. About $20 per 1,000 questions.',
      weak: '11 empty first attempts, all recovered by the automatic retry.',
      vsBest: 'Same quality as GLM, more dependable, about 4.5× the cost.',
    },
    {
      model: 'deepseek/deepseek-v4.1-flash',
      quality: 0.674,
      priceIn: 0.045,
      priceOut: 0.5,
      good: 'Most correct facts and best at combining sources.',
      weak: 'Slowest (about 83 seconds per answer); 17 empty first attempts.',
      vsBest: 'Same overall quality, noticeably slower.',
    },
  ],
  recommend: [
    {
      model: 'openai/gpt-6-luna',
      quality: 0.797,
      priceIn: 0.1,
      priceOut: 0.5,
      recommended: true,
      good: 'Best grounded in the evidence, no failures, mid-priced.',
      weak: 'Not the cheapest.',
      vsBest: 'Top scorer.',
    },
    {
      model: 'z-ai/glm-5.3-flash',
      quality: 0.76,
      priceIn: 0.0313,
      priceOut: 0.0846,
      good: 'Cheapest and fastest; best follow-up questions.',
      weak: 'Cites its evidence a little less exactly.',
      vsBest: 'Slightly lower, about 40% of the cost.',
    },
    {
      model: 'deepseek/deepseek-v4.1-flash',
      quality: 0.758,
      priceIn: 0.045,
      priceOut: 0.5,
      good: 'Solid recommendations.',
      weak: '6 cut-off replies needed a retry; slow on some items.',
      vsBest: 'Slightly lower, slower, more expensive.',
    },
  ],
  grade: [
    {
      model: 'openai/gpt-6-luna',
      quality: 0.88,
      priceIn: 0.1,
      priceOut: 0.5,
      recommended: true,
      good: 'Agrees most with careful grading, caught every planted contradiction, fewest false alarms.',
      weak: 'One of ten repeat gradings differed.',
      vsBest: 'Top scorer.',
    },
    {
      model: 'anthropic/claude-haiku-5.5',
      quality: 0.796,
      priceIn: 0.1,
      priceOut: 0.5,
      good: 'Fast, consistent, no bias in scores.',
      weak: 'Missed 2 of 9 planted contradictions, so it can grade too generously.',
      vsBest: 'Lower; more likely to let a wrong answer pass.',
    },
    {
      model: 'deepseek/deepseek-v4.1-flash',
      quality: 0.796,
      priceIn: 0.045,
      priceOut: 0.5,
      good: 'Good agreement with careful grading.',
      weak: 'Least consistent on repeat grading (7 of 10), slow.',
      vsBest: 'Lower and less consistent.',
    },
  ],
};
