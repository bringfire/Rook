import { describe, expect, it } from "vitest";
import {
  classifyConfiguration, classifyTrial, nearestRank, summarizeSamples,
} from "../src/metrics.js";

describe("metrics", () => {
  it("uses nearest-rank percentiles", () => {
    const values = Array.from({ length: 100 }, (_, index) => index + 1);
    expect(nearestRank(values, 0.5)).toBe(50);
    expect(nearestRank(values, 0.95)).toBe(95);
    expect(nearestRank(values, 0.99)).toBe(99);
  });

  it("does not invent empty statistics", () => {
    expect(summarizeSamples([])).toEqual({
      count: 0, average: null, p50: null, p95: null, p99: null, max: null,
    });
  });

  it("uses the slower valid CPU or GPU p95", () => {
    expect(classifyTrial({
      status: "completed", correctnessPassed: true, constructionMs: 200,
      cpu: { p95: 8, p99: 12 },
      gpu: { validCount: 300, p95: 20, p99: 22 },
    })).toMatchObject({ tier: "preview-viable", basis: "cpu_and_gpu", frameP95: 20 });
  });

  it("uses CPU proxy below 270 GPU samples", () => {
    expect(classifyTrial({
      status: "completed", correctnessPassed: true, constructionMs: 200,
      cpu: { p95: 12, p99: 20 },
      gpu: { validCount: 269, p95: 6, p99: 8 },
    })).toMatchObject({ tier: "interactive", basis: "cpu_proxy_only" });
  });

  it("uses the worst completed trial, not pooled samples", () => {
    expect(classifyConfiguration([
      { status: "completed", classification: { tier: "interactive" } },
      { status: "completed", classification: { tier: "marginal" } },
      { status: "completed", classification: { tier: "preview-viable" } },
    ])).toEqual({ tier: "marginal", source: "worst_completed_trial", trialIndex: 1 });
  });

  it("makes an aborted trial impractical", () => {
    expect(classifyConfiguration([
      { status: "completed", classification: { tier: "interactive" } },
      { status: "aborted", reason: "context_lost" },
    ])).toEqual({ tier: "impractical", source: "aborted_trial", trialIndex: 1 });
  });
});
