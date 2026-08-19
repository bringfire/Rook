import { mkdirSync, realpathSync, writeFileSync } from "node:fs";
import { isAbsolute, join, normalize, relative, resolve } from "node:path";
import { pathToFileURL } from "node:url";

function requireInside(root: string, candidate: string, label: string): void {
	const rel = relative(root, candidate);
	if (rel === "" || (!rel.startsWith("..") && !isAbsolute(rel))) return;
	throw new Error(`${label}_outside_prime_worktree:${candidate}`);
}

async function main(): Promise<void> {
	const [rawPrimeRoot, rawEvidenceRoot, rawBudget, rawRookFullRoot] = process.argv.slice(2);
	const budget = Number(rawBudget);
	if (
		!rawPrimeRoot ||
		!rawEvidenceRoot ||
		!rawRookFullRoot ||
		!Number.isSafeInteger(budget) ||
		budget <= 0
	) {
		throw new Error(
			"usage: prime_upstream_compatibility_preflight <prime-root> <evidence-root> <token-budget> <rook-full-root>",
		);
	}

	const primeRoot = normalize(realpathSync(resolve(rawPrimeRoot)));
	const evidenceRoot = resolve(rawEvidenceRoot);
	const rookFullRoot = normalize(realpathSync(resolve(rawRookFullRoot)));
	const python = process.env.PRIME_AGENT_KERNEL_PYTHON;
	if (!python) throw new Error("PRIME_AGENT_KERNEL_PYTHON_missing");
	mkdirSync(evidenceRoot, { recursive: true });

	const ipythonPath = realpathSync(
		join(primeRoot, "packages/coding-agent/src/core/tools/ipython.ts"),
	);
	requireInside(primeRoot, ipythonPath, "node_import");
	const { IpythonKernelProvisioner } = await import(pathToFileURL(ipythonPath).href);
	const goalRoot = realpathSync(join(primeRoot, "packages/coding-agent/skills/goal"));
	const snapshotDir = join(evidenceRoot, "kernel-state");
	mkdirSync(snapshotDir, { recursive: true });

	const requests: string[] = [];
	let goalStatus = "active";
	const hostHandlers = {
		"goal.get": async () => {
			requests.push("goal.get");
			return {
				goal: {
					objective: "disposable upstream compatibility preflight",
					status: goalStatus,
					token_budget: budget,
					tokens_used: 0,
				},
				remaining_tokens: budget,
				completion_budget_report: null,
			};
		},
		"goal.complete": async () => {
			requests.push("goal.complete");
			goalStatus = "complete";
			return {
				goal: {
					objective: "disposable upstream compatibility preflight",
					status: goalStatus,
					token_budget: budget,
					tokens_used: 0,
				},
				remaining_tokens: budget,
				completion_budget_report: "preflight complete",
			};
		},
	};
	const makeProvisioner = () =>
		new IpythonKernelProvisioner(evidenceRoot, {
			python,
			snapshotDir,
			pythonSkills: [
				{
					name: "goal",
					importName: "goal",
					packagePath: goalRoot,
					pyprojectPath: join(goalRoot, "pyproject.toml"),
				},
				{
					name: "rook-full",
					importName: "rook_full",
					packagePath: rookFullRoot,
					pyprojectPath: join(rookFullRoot, "pyproject.toml"),
				},
			],
			hostHandlers,
		});

	const first = makeProvisioner();
	let firstKernelClosed = false;
	let firstRecord: Record<string, unknown> | undefined;
	let snapshotRecord: Record<string, unknown> | undefined;
	let pruned: string[] | null = null;
	try {
		const manager = await first.ensure();
		const execution = await manager.execute(`
import json
import sys
import goal as _goal_module
import rlm.mcp_base as _mcp_base_module
import rook_full as _rook_full_module
sentinel = {"state": "survives", "value": 42}
large_text = "x" * (17 * 1024 * 1024)
_before = await _goal_module.get()
print(json.dumps({
    "pythonExecutable": sys.executable,
    "goalFile": _goal_module.__file__,
    "mcpBaseFile": _mcp_base_module.__file__,
    "rookFullFile": _rook_full_module.__file__,
    "getStatus": _before["goal"]["status"],
    "getTokenBudget": _before["goal"]["token_budget"],
}, sort_keys=True))
`);
		if (execution.status !== "ok") throw new Error(`preflight_kernel_execution_${execution.status}`);
		firstRecord = JSON.parse(execution.stdout.trim().split(/\r?\n/).at(-1) ?? "null");
		const mcpBaseFile = normalize(realpathSync(String(firstRecord?.mcpBaseFile)));
		const goalFile = normalize(realpathSync(String(firstRecord?.goalFile)));
		requireInside(primeRoot, mcpBaseFile, "python_mcp_base_import");
		requireInside(primeRoot, goalFile, "python_goal_import");

		const snapshot = await manager.snapshotState();
		if (!snapshot) throw new Error("snapshot_missing");
		snapshotRecord = {
			saved: snapshot.saved,
			skipped: snapshot.skipped,
		};
		if (!snapshot.saved.includes("sentinel")) throw new Error("sentinel_not_snapshotted");
		if (!snapshot.skipped.some(({ name }) => name === "large_text")) {
			throw new Error("oversized_state_not_detected");
		}

		pruned = await first.pruneOversizedVariables();
		if (!pruned?.includes("large_text")) throw new Error("oversized_state_not_pruned");
		const afterPrune = await manager.execute(`
import json
_after_prune = await _goal_module.get()
print(json.dumps({
    "goalStatus": _after_prune["goal"]["status"],
    "sentinel": sentinel,
    "largeTextPresent": "large_text" in globals(),
}, sort_keys=True))
`);
		if (afterPrune.status !== "ok") throw new Error(`post_prune_execution_${afterPrune.status}`);
		const afterPruneRecord = JSON.parse(afterPrune.stdout.trim().split(/\r?\n/).at(-1) ?? "null");
		if (afterPruneRecord.goalStatus !== "active") throw new Error("goal_not_active_after_prune");
		if (afterPruneRecord.largeTextPresent !== false) throw new Error("oversized_state_still_present");
		if (afterPruneRecord.sentinel?.state !== "survives" || afterPruneRecord.sentinel?.value !== 42) {
			throw new Error("sentinel_lost_after_prune");
		}

		const completion = await manager.execute(`
import json
_completed = await _goal_module.complete()
print(json.dumps({"goalStatus": _completed["goal"]["status"]}, sort_keys=True))
`);
		if (completion.status !== "ok") throw new Error(`completion_execution_${completion.status}`);
		const completionRecord = JSON.parse(completion.stdout.trim().split(/\r?\n/).at(-1) ?? "null");
		if (completionRecord.goalStatus !== "complete") throw new Error("goal_not_completed");
	} finally {
		await first.dispose();
		firstKernelClosed = true;
	}

	const second = makeProvisioner();
	let secondKernelClosed = false;
	let restoreRecord: Record<string, unknown> | undefined;
	try {
		const manager = await second.ensure();
		const restored = await manager.execute(`
import json
import rlm.mcp_base as _restored_mcp_base
_restored_goal = await goal.get()
print(json.dumps({
    "goalStatus": _restored_goal["goal"]["status"],
    "mcpBaseFile": _restored_mcp_base.__file__,
    "sentinel": sentinel,
    "largeTextPresent": "large_text" in globals(),
}, sort_keys=True))
`);
		if (restored.status !== "ok") throw new Error(`restore_execution_${restored.status}`);
		restoreRecord = JSON.parse(restored.stdout.trim().split(/\r?\n/).at(-1) ?? "null");
		const restoredMcpBase = normalize(realpathSync(String(restoreRecord?.mcpBaseFile)));
		requireInside(primeRoot, restoredMcpBase, "restored_python_mcp_base_import");
		if (restoreRecord.goalStatus !== "complete") {
			throw new Error("host_goal_bridge_not_reconnected");
		}
		if (restoreRecord.largeTextPresent !== false) throw new Error("pruned_state_restored");
		if (restoreRecord.sentinel?.state !== "survives" || restoreRecord.sentinel?.value !== 42) {
			throw new Error("sentinel_not_restored");
		}
	} finally {
		await second.dispose();
		secondKernelClosed = true;
	}

	const record = {
		schema: "rook.experiment.prime_upstream_compatibility_preflight:v1",
		primeRoot,
		nodeImportFile: ipythonPath,
		first: firstRecord,
		snapshot: snapshotRecord,
		pruned,
		restored: restoreRecord,
		requests,
		firstKernelClosed,
		secondKernelClosed,
	};
	const serialized = `${JSON.stringify(record, null, 2)}\n`;
	writeFileSync(join(evidenceRoot, "preflight-result.json"), serialized, "utf8");
	process.stdout.write(serialized);
}

main().catch((error: unknown) => {
	process.stderr.write(`${error instanceof Error ? error.stack ?? error.message : String(error)}\n`);
	process.exitCode = 1;
});
