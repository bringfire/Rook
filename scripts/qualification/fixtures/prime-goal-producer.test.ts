// Local, read-only producer oracle. Run with the pinned Prime coding-agent Vitest config.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, vi } from "vitest";

vi.hoisted(() => {
  delete process.env.PI_PACKAGE_DIR;
  process.env.DO_NOT_TRACK = "1";
});
vi.mock("child_process", () => {
  const refuse = () => { throw new Error("producer oracle forbids child processes"); };
  return Object.fromEntries(["spawn", "spawnSync", "exec", "execSync", "execFile", "execFileSync", "fork"].map(name => [name, refuse]));
});
vi.mock("net", () => ({ connect: () => { throw new Error("producer oracle forbids sockets"); } }));
vi.stubGlobal("fetch", () => { throw new Error("producer oracle forbids network"); });

test("pinned Prime loader and formatter classify the shipped goal package", async () => {
  const { loadSkillsFromDir, formatSkillsForPrompt } = await import("D:/prime-agent/.worktrees/rookchat-prime-final-series/packages/coding-agent/src/core/skills.ts");
  const here = dirname(fileURLToPath(import.meta.url));
  const protocol = JSON.parse(readFileSync(join(here, "../protocols/rookchat-prime-acp-precontact-v3.json"), "utf8"));
  const dir = join(dirname(protocol.runtime.manifestPath), "skills/goal");
  const result = loadSkillsFromDir({ dir, source: "explicit" });
  expect(result.diagnostics).toEqual([]);
  expect(result.skills).toHaveLength(1);
  const skill = result.skills[0];
  expect(skill.name).toBe("goal");
  expect(skill.kind).toBe("python");
  if (skill.kind !== "python") throw new Error("shipped goal is not Python-backed");
  expect(skill.python.importName).toBe("goal");
  expect(skill.filePath).toBe(join(dir, "SKILL.md"));
  const recorded = JSON.parse(readFileSync(join(here, "prime-goal-advertisement.json"), "utf8"));
  expect({ location: skill.filePath, text: formatSkillsForPrompt(result.skills) }).toEqual(recorded);
});
