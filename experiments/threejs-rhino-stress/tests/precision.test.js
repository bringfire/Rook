import { expect, it, vi } from "vitest";
import { createGpuTimer } from "../src/gpu-timer.js";
import * as precision from "../src/precision.js";

const {
  comparePixelBuffers,
  PRECISION_SAMPLE_TIMES,
  readScenePixels,
} = precision;

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

it("compares paired coordinate scenes at every required sample time", () => {
  expect(precision.compareCoordinateScenes).toBeTypeOf("function");
  const rebased = {
    scene: { name: "rebased", updateMatrixWorld: vi.fn() },
    camera: {},
    time: null,
  };
  const large = {
    scene: { name: "large", updateMatrixWorld: vi.fn() },
    camera: {},
    time: null,
  };
  const contexts = new Map([
    [rebased.scene, rebased],
    [large.scene, large],
  ]);
  const evaluated = [];
  let renderedScene = null;
  const renderer = {
    getRenderTarget: () => null,
    getActiveCubeFace: () => 0,
    getActiveMipmapLevel: () => 0,
    setRenderTarget: vi.fn(),
    render: vi.fn((scene) => {
      renderedScene = scene;
    }),
    readRenderTargetPixels: vi.fn((_target, _x, _y, _width, _height, pixels) => {
      const context = contexts.get(renderedScene);
      pixels[0] = context.scene.name === "large" ? context.time * 2 + 1 : context.time * 2;
    }),
  };

  const samples = precision.compareCoordinateScenes({
    renderer,
    rebased,
    large,
    evaluate(context, time) {
      context.time = time;
      evaluated.push([context.scene.name, time]);
    },
  });

  expect(evaluated).toEqual([
    ["rebased", 0], ["large", 0],
    ["rebased", 0.5], ["large", 0.5],
    ["rebased", 1], ["large", 1],
  ]);
  expect(samples).toHaveLength(3);
  expect(samples.map(({ time, pass }) => ({ time, pass }))).toEqual([
    { time: 0, pass: true },
    { time: 0.5, pass: true },
    { time: 1, pass: true },
  ]);
  expect(renderer.render).toHaveBeenCalledTimes(6);
  expect(rebased.scene.updateMatrixWorld).toHaveBeenCalledTimes(3);
  expect(large.scene.updateMatrixWorld).toHaveBeenCalledTimes(3);
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
