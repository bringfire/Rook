const TIER_RANK = {
  interactive: 0, "preview-viable": 1, marginal: 2, impractical: 3,
};

export function nearestRank(values, quantile) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.max(1, Math.ceil(quantile * sorted.length)) - 1];
}

export function summarizeSamples(values) {
  if (!values.length) {
    return { count: 0, average: null, p50: null, p95: null, p99: null, max: null };
  }
  if (values.some((value) => !Number.isFinite(value))) {
    throw new Error("samples must contain only finite durations");
  }
  return {
    count: values.length,
    average: values.reduce((sum, value) => sum + value, 0) / values.length,
    p50: nearestRank(values, 0.5),
    p95: nearestRank(values, 0.95),
    p99: nearestRank(values, 0.99),
    max: Math.max(...values),
  };
}

export function classifyTrial({ status, correctnessPassed, constructionMs, cpu, gpu }) {
  if (status !== "completed" || !correctnessPassed) {
    return { tier: "impractical", basis: "trial_failure", frameP95: null, frameP99: null };
  }
  if (!Number.isFinite(constructionMs)
      || !Number.isFinite(cpu?.p95)
      || !Number.isFinite(cpu?.p99)) {
    return {
      tier: "impractical", basis: "invalid_metrics",
      frameP95: null, frameP99: null,
    };
  }
  if (constructionMs > 30000) {
    return { tier: "impractical", basis: "trial_failure", frameP95: null, frameP99: null };
  }
  if (gpu?.validCount >= 270
      && (!Number.isFinite(gpu?.p95) || !Number.isFinite(gpu?.p99))) {
    return {
      tier: "impractical", basis: "invalid_metrics",
      frameP95: null, frameP99: null,
    };
  }
  const gpuValid = gpu?.validCount >= 270;
  const basis = gpuValid ? "cpu_and_gpu" : "cpu_proxy_only";
  const frameP95 = gpuValid ? Math.max(cpu.p95, gpu.p95) : cpu.p95;
  const frameP99 = gpuValid ? Math.max(cpu.p99, gpu.p99) : cpu.p99;
  let tier = "interactive";
  if (frameP95 > 100) tier = "impractical";
  else if (constructionMs > 10000 || frameP95 > 33.33) tier = "marginal";
  else if (frameP95 > 16.67 || frameP99 > 33.33) tier = "preview-viable";
  return { tier, basis, frameP95, frameP99 };
}

export function classifyConfiguration(trials) {
  const aborted = trials.findIndex((trial) => trial.status !== "completed");
  if (aborted >= 0) return { tier: "impractical", source: "aborted_trial", trialIndex: aborted };
  if (!trials.length) return { tier: "impractical", source: "no_completed_trial", trialIndex: null };
  let worst = 0;
  for (let index = 1; index < trials.length; index += 1) {
    if (TIER_RANK[trials[index].classification.tier] >
        TIER_RANK[trials[worst].classification.tier]) worst = index;
  }
  return {
    tier: trials[worst].classification.tier,
    source: "worst_completed_trial",
    trialIndex: worst,
  };
}
