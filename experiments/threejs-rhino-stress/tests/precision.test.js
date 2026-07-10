import { expect, it, vi } from "vitest";
import { createGpuTimer } from "../src/gpu-timer.js";
import {
  comparePixelBuffers,
  PRECISION_SAMPLE_TIMES,
  readScenePixels,
} from "../src/precision.js";

vi.mock("three", () => ({
  WebGLRenderTarget: class {
    constructor(width, height) {
      this.width = width;
      this.height = height;
      this.disposed = false;
    }

    dispose() {
      this.disposed = true;
    }
  },
}));

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

it("discards every pending query when a GPU disjoint is observed", () => {
  const extension = {
    TIME_ELAPSED_EXT: "TIME_ELAPSED_EXT",
    GPU_DISJOINT_EXT: "GPU_DISJOINT_EXT",
  };
  const query = {};
  let available = false;
  let disjoint = true;
  const gl = {
    QUERY_RESULT_AVAILABLE: "QUERY_RESULT_AVAILABLE",
    QUERY_RESULT: "QUERY_RESULT",
    getExtension: vi.fn(() => extension),
    createQuery: vi.fn(() => query),
    beginQuery: vi.fn(),
    endQuery: vi.fn(),
    getParameter: vi.fn(() => disjoint),
    getQueryParameter: vi.fn((_, parameter) => (
      parameter === "QUERY_RESULT_AVAILABLE" ? available : 7000000
    )),
    deleteQuery: vi.fn(),
  };
  const timer = createGpuTimer(gl);

  timer.begin();
  timer.end();
  timer.poll();

  expect(gl.deleteQuery).toHaveBeenCalledWith(query);
  expect(timer.snapshot()).toEqual({
    available: true,
    samplesMs: [],
    disjointCount: 1,
    pendingCount: 0,
  });

  available = true;
  disjoint = false;
  timer.poll();
  expect(timer.snapshot().samplesMs).toEqual([]);
});

it.each(["render", "readRenderTargetPixels"])(
  "restores the full render-target state when %s throws",
  (failingMethod) => {
    const previousTarget = {};
    const renderer = {
      getRenderTarget: vi.fn(() => previousTarget),
      getActiveCubeFace: vi.fn(() => 4),
      getActiveMipmapLevel: vi.fn(() => 2),
      setRenderTarget: vi.fn(),
      render: vi.fn(() => {
        if (failingMethod === "render") throw new Error("render failed");
      }),
      readRenderTargetPixels: vi.fn(() => {
        if (failingMethod === "readRenderTargetPixels") {
          throw new Error("readRenderTargetPixels failed");
        }
      }),
    };

    expect(() => readScenePixels(renderer, {}, {})).toThrow(`${failingMethod} failed`);

    const temporaryTarget = renderer.setRenderTarget.mock.calls[0][0];
    expect(renderer.setRenderTarget).toHaveBeenLastCalledWith(
      previousTarget,
      4,
      2,
    );
    expect(temporaryTarget.disposed).toBe(true);
  },
);
