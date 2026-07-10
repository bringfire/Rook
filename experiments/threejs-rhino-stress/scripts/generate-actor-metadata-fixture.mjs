import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { buildActorMetadataGlb, sha256Hex } from "./fixture-builder.mjs";

const output = resolve(dirname(fileURLToPath(import.meta.url)), "../fixtures");
const bytes = buildActorMetadataGlb();
await mkdir(output, { recursive: true });
await writeFile(resolve(output, "actor-metadata.glb"), bytes);
await writeFile(resolve(output, "actor-metadata.sha256"),
  sha256Hex(bytes) + "\n", "utf8");
