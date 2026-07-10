import { describe, expect, it } from "vitest";
import { APP_TITLE } from "../src/main.js";

describe("scaffold", () => {
  it("uses the fixed title", () => {
    expect(APP_TITLE).toBe("Rook Three.js Rhino Stress Harness");
  });
});
