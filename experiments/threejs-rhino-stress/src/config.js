export const ACTOR_PRESETS = Object.freeze([100, 338, 1000, 10000]);
export const LARGE_WORLD_OFFSET = Object.freeze([300000, -200000, 20000]);

export const BENCHMARK_PROTOCOL = Object.freeze({
  width: 1920,
  height: 1080,
  pixelRatio: 1,
  warmupFrames: 120,
  measuredFrames: 300,
  trials: 3,
  gpuValidSampleFloor: 270,
});

export const DEFAULT_CONFIG = Object.freeze({
  actorCount: 338,
  geometryDensity: 1,
  geometryOwnership: "shared",
  motionGranularity: "individual",
  coordinateMode: "rebased",
  materialOwnership: "shared",
  contextMode: "unbatched",
});
