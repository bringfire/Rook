import { afterEach, expect, it, vi } from "vitest";
import { buildActorIndex } from "../src/actor-index.js";
import {
  captureEnvironment, runCorrectnessChecks, validateProtocolEnvironment,
} from "../src/evidence.js";
import { countScene, createSyntheticScene } from "../src/scene-generator.js";

afterEach(() => vi.unstubAllGlobals());

it("invalidates hidden or resized trials", () => {
  expect(() => validateProtocolEnvironment({
    visibilityState: "hidden", width: 1920, height: 1080,
  })).toThrow(/visible/);
  expect(() => validateProtocolEnvironment({
    visibilityState: "visible", width: 960, height: 540,
  })).toThrow(/1920 x 1080/);
});

it("checks deterministic seek, independent transforms, and pivots", () => {
  const context = createSyntheticScene({ actorCount: 3 });
  context.actors[0].scale.set(2, 3, 4);
  context.actorIndex = buildActorIndex(context.scene).actors;
  context.motionGranularity = "individual";
  expect(runCorrectnessChecks(context)).toEqual({
    pass: true,
    deterministicSeek: true,
    independentTransform: true,
    pivotSanity: { status: "passed" },
  });
});

it("reports arbitrary local-GLB pivot validation as unavailable", () => {
  const context = createSyntheticScene({ actorCount: 3 });
  context.sourceKind = "local_glb";
  context.actorIndex = buildActorIndex(context.scene).actors;
  context.motionGranularity = "individual";
  const result = runCorrectnessChecks(context);
  expect(result.pass).toBe(true);
  expect(result.pivotSanity).toEqual({
    status: "unavailable",
    reason: "arbitrary local GLB pivot semantics are outside this experiment",
  });
});

it("captures browser, drawing-buffer, GPU, and heap evidence", () => {
  vi.stubGlobal("navigator", { userAgent: "vitest", platform: "test" });
  vi.stubGlobal("window", {
    devicePixelRatio: 1,
    visualViewport: { scale: 1 },
  });
  const debug = {
    UNMASKED_VENDOR_WEBGL: "vendor",
    UNMASKED_RENDERER_WEBGL: "renderer",
  };
  const gl = {
    getExtension: () => debug,
    getParameter: (key) => key,
  };
  const renderer = {
    domElement: { width: 1920, height: 1080 },
    getContext: () => gl,
  };

  expect(captureEnvironment(renderer)).toMatchObject({
    userAgent: "vitest",
    platform: "test",
    devicePixelRatio: 1,
    visualViewportScale: 1,
    drawingBuffer: [1920, 1080],
    gpuVendor: "vendor",
    gpuRenderer: "renderer",
  });
});

it("counts complete scene structure", () => {
  expect(countScene(createSyntheticScene({ actorCount: 3 }).scene))
    .toMatchObject({
      nodes: 33,
      actors: 3,
      geometries: 2,
      meshes: 27,
      materials: 3,
      triangles: 324,
    });
});
