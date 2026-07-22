export type SourceReaderBudgetLimits = {
  maxReadCalls: number;
  maxInputTokens: number;
  maxEstimatedCostUsd: number;
  estimatedInputCostPerMillionTokensUsd: number;
  maxRepairAttempts: number;
  maxConcurrency: number;
};

export type SourceReaderBudgetSnapshot = {
  readCalls: number;
  inputTokens: number;
  estimatedCostUsd: number;
  repairAttempts: number;
  limits: SourceReaderBudgetLimits;
};

export class SourceReaderBudgetExceededError extends Error {
  readonly check:
    | 'max_read_calls'
    | 'max_input_tokens'
    | 'max_estimated_cost_usd'
    | 'max_repair_attempts'
    | 'max_concurrency';

  constructor(check: SourceReaderBudgetExceededError['check'], detail: string) {
    super(`[source-reader-budget] ${check}: ${detail}`);
    this.name = 'SourceReaderBudgetExceededError';
    this.check = check;
  }
}

export class SourceReaderBudget {
  private readCalls = 0;
  private inputTokens = 0;
  private estimatedCostUsd = 0;
  private repairAttempts = 0;

  constructor(readonly limits: SourceReaderBudgetLimits) {
    if (!Number.isInteger(limits.maxReadCalls) || limits.maxReadCalls < 1) {
      throw new SourceReaderBudgetExceededError(
        'max_read_calls',
        `Configured read-call cap must be a positive integer; got ${limits.maxReadCalls}.`,
      );
    }
    if (!Number.isInteger(limits.maxInputTokens) || limits.maxInputTokens < 1) {
      throw new SourceReaderBudgetExceededError(
        'max_input_tokens',
        `Configured input-token cap must be a positive integer; got ${limits.maxInputTokens}.`,
      );
    }
    if (!Number.isFinite(limits.maxEstimatedCostUsd) || limits.maxEstimatedCostUsd <= 0) {
      throw new SourceReaderBudgetExceededError(
        'max_estimated_cost_usd',
        `Configured cost cap must be positive; got ${limits.maxEstimatedCostUsd}.`,
      );
    }
    if (
      !Number.isFinite(limits.estimatedInputCostPerMillionTokensUsd) ||
      limits.estimatedInputCostPerMillionTokensUsd < 0
    ) {
      throw new SourceReaderBudgetExceededError(
        'max_estimated_cost_usd',
        `Configured cost estimate rate must be non-negative; got ${limits.estimatedInputCostPerMillionTokensUsd}.`,
      );
    }
    if (!Number.isInteger(limits.maxRepairAttempts) || limits.maxRepairAttempts < 0) {
      throw new SourceReaderBudgetExceededError(
        'max_repair_attempts',
        `Configured repair cap must be a non-negative integer; got ${limits.maxRepairAttempts}.`,
      );
    }
    if (!Number.isInteger(limits.maxConcurrency) || limits.maxConcurrency < 1) {
      throw new SourceReaderBudgetExceededError(
        'max_concurrency',
        `Configured concurrency must be a positive integer; got ${limits.maxConcurrency}.`,
      );
    }
  }

  reserveRead(args: { estimatedInputTokens: number; label: string }): void {
    const tokens = Math.max(0, Math.ceil(args.estimatedInputTokens));
    const nextReadCalls = this.readCalls + 1;
    const nextInputTokens = this.inputTokens + tokens;
    const nextCost =
      this.estimatedCostUsd +
      (tokens / 1_000_000) * this.limits.estimatedInputCostPerMillionTokensUsd;
    if (nextReadCalls > this.limits.maxReadCalls) {
      throw new SourceReaderBudgetExceededError(
        'max_read_calls',
        `${args.label} would use read ${nextReadCalls}/${this.limits.maxReadCalls}.`,
      );
    }
    if (nextInputTokens > this.limits.maxInputTokens) {
      throw new SourceReaderBudgetExceededError(
        'max_input_tokens',
        `${args.label} would use ${nextInputTokens}/${this.limits.maxInputTokens} estimated input tokens.`,
      );
    }
    if (nextCost > this.limits.maxEstimatedCostUsd) {
      throw new SourceReaderBudgetExceededError(
        'max_estimated_cost_usd',
        `${args.label} would cost an estimated $${nextCost.toFixed(4)} against the $${this.limits.maxEstimatedCostUsd.toFixed(4)} cap.`,
      );
    }
    this.readCalls = nextReadCalls;
    this.inputTokens = nextInputTokens;
    this.estimatedCostUsd = nextCost;
  }

  reserveRepair(label: string): void {
    const next = this.repairAttempts + 1;
    if (next > this.limits.maxRepairAttempts) {
      throw new SourceReaderBudgetExceededError(
        'max_repair_attempts',
        `${label} would use repair ${next}/${this.limits.maxRepairAttempts}.`,
      );
    }
    this.repairAttempts = next;
  }

  snapshot(): SourceReaderBudgetSnapshot {
    return {
      readCalls: this.readCalls,
      inputTokens: this.inputTokens,
      estimatedCostUsd: this.estimatedCostUsd,
      repairAttempts: this.repairAttempts,
      limits: this.limits,
    };
  }
}

export async function mapWithConcurrency<TInput, TOutput>(args: {
  inputs: readonly TInput[];
  concurrency: number;
  run: (input: TInput, index: number) => Promise<TOutput>;
}): Promise<TOutput[]> {
  if (!Number.isInteger(args.concurrency) || args.concurrency < 1) {
    throw new SourceReaderBudgetExceededError(
      'max_concurrency',
      `Concurrency must be a positive integer; got ${args.concurrency}.`,
    );
  }
  const output = new Array<TOutput>(args.inputs.length);
  let nextIndex = 0;
  const workers = Array.from(
    { length: Math.min(args.concurrency, args.inputs.length) },
    async () => {
      while (true) {
        const index = nextIndex++;
        if (index >= args.inputs.length) return;
        output[index] = await args.run(args.inputs[index]!, index);
      }
    },
  );
  await Promise.all(workers);
  return output;
}
