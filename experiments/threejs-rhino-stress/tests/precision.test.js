import { expect, it } from "vitest";
import { comparePixelBuffers, PRECISION_SAMPLE_TIMES } from "../src/precision.js";

it("uses required sample times", () => {
  expect(PRECISION_SAMPLE_TIMES).toEqual([0, 0.5, 1]);
});

it("passes within tolerance and fails above it", () => {
  expect(comparePixelBuffers(
    new Uint8Array([10, 20, 30, 255]),
    new Uint8Array([10, 20, 31, 255]),
  ).pass).toBe(true);
  const left = new Uint8Array(400);
  const right = new Uint8Array(400);
  right.fill(10, 0, 8);
  expect(comparePixelBuffers(left, right).pass).toBe(false);
});
