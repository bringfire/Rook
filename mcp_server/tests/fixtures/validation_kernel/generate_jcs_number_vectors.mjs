import { readFileSync, writeFileSync } from "node:fs";
import { EOL } from "node:os";
import { fileURLToPath } from "node:url";

const VECTOR_COUNT = 20_000;
const MASK_64 = (1n << 64n) - 1n;
const TARGET = fileURLToPath(
  new URL("./jcs_number_vectors.jsonl", import.meta.url),
);
const view = new DataView(new ArrayBuffer(8));
const rows = [];
const usedBits = new Set();

function normalizeBits(bits) {
  return bits.toString(16).padStart(16, "0");
}

function numberFromBits(bits) {
  view.setBigUint64(0, BigInt(`0x${bits}`), false);
  return view.getFloat64(0, false);
}

function bitsFromNumber(value) {
  view.setFloat64(0, value, false);
  return normalizeBits(view.getBigUint64(0, false));
}

function addRow(caseId, group, relation, bits, allowDuplicate = false) {
  const normalized = normalizeBits(BigInt(`0x${bits}`));
  const value = numberFromBits(normalized);
  if (!Number.isFinite(value)) {
    throw new Error(`non-finite directed vector: ${caseId}`);
  }
  if (!allowDuplicate && usedBits.has(normalized)) {
    return;
  }
  usedBits.add(normalized);
  rows.push({
    case_id: caseId,
    group,
    relation,
    bits: normalized,
    canonical: JSON.stringify(value),
  });
}

function addPositiveNeighborhood(
  group,
  casePrefix,
  centerBits,
  allowDuplicate = false,
) {
  const center = BigInt(`0x${centerBits}`);
  addRow(
    `${casePrefix}_next_down`,
    group,
    "next_down",
    normalizeBits(center - 1n),
    allowDuplicate,
  );
  addRow(
    `${casePrefix}_center`,
    group,
    "center",
    normalizeBits(center),
    allowDuplicate,
  );
  const next = center + 1n;
  if (next < 0x7ff0000000000000n) {
    addRow(
      `${casePrefix}_next_up`,
      group,
      "next_up",
      normalizeBits(next),
      allowDuplicate,
    );
  }
}

addRow("positive_zero", "signed_zero", "positive_zero", "0000000000000000");
addRow("negative_zero", "signed_zero", "negative_zero", "8000000000000000");

addPositiveNeighborhood(
  "decimal_fixed_transition",
  "one_e_minus_6",
  bitsFromNumber(1e-6),
);
addPositiveNeighborhood(
  "large_fixed_transition",
  "one_e_21",
  bitsFromNumber(1e21),
);
addPositiveNeighborhood(
  "integer_precision_transition",
  "two_pow_53",
  bitsFromNumber(2 ** 53),
);
addPositiveNeighborhood(
  "minimum_subnormal",
  "minimum_positive_subnormal",
  "0000000000000001",
  true,
);

addRow(
  "maximum_subnormal_next_down",
  "normal_boundary",
  "max_subnormal_next_down",
  "000ffffffffffffe",
);
addRow(
  "maximum_subnormal",
  "normal_boundary",
  "max_subnormal",
  "000fffffffffffff",
);
addRow(
  "minimum_normal",
  "normal_boundary",
  "min_normal",
  "0010000000000000",
);
addRow(
  "minimum_normal_next_up",
  "normal_boundary",
  "min_normal_next_up",
  "0010000000000001",
);

addPositiveNeighborhood(
  "maximum_finite",
  "maximum_finite",
  "7fefffffffffffff",
);

for (const bits of [
  "41b3de4355555553",
  "41b3de4355555554",
  "41b3de4355555555",
  "41b3de4355555556",
  "41b3de4355555557",
  "43143ff3c1cb0959",
]) {
  addRow(
    `rfc8785_${bits}`,
    "rfc8785_halfway",
    "appendix_b",
    bits,
  );
}

for (const bits of [
  "8000000000000001",
  "ffefffffffffffff",
  "c340000000000000",
  "4430000000000000",
  "444b1ae4d6e2ef4e",
  "44b52d02c7e14af5",
  "44b52d02c7e14af6",
  "44b52d02c7e14af7",
  "becbf647612f3696",
]) {
  addRow(
    `rfc8785_${bits}`,
    "rfc8785_appendix_b",
    "appendix_b",
    bits,
  );
}

let state = 0x6a09e667f3bcc909n;
function nextRandomBits() {
  state ^= state >> 12n;
  state ^= (state << 25n) & MASK_64;
  state ^= state >> 27n;
  state &= MASK_64;
  return (state * 0x2545f4914f6cdd1dn) & MASK_64;
}

let randomIndex = 0;
while (rows.length < VECTOR_COUNT) {
  const bits = normalizeBits(nextRandomBits());
  const value = numberFromBits(bits);
  if (!Number.isFinite(value) || usedBits.has(bits)) {
    continue;
  }
  addRow(
    `random_${String(randomIndex).padStart(5, "0")}`,
    "fixed_seed_random",
    "sample",
    bits,
  );
  randomIndex += 1;
}

const content = `${rows.map((row) => JSON.stringify(row)).join(EOL)}${EOL}`;
if (process.argv.includes("--check")) {
  let existing;
  try {
    existing = readFileSync(TARGET, "utf8");
  } catch {
    console.error(`missing generated fixture: ${TARGET}`);
    process.exit(1);
  }
  if (existing !== content) {
    console.error("jcs_number_vectors.jsonl is not reproducible");
    process.exit(1);
  }
} else {
  writeFileSync(TARGET, content, "utf8");
}
