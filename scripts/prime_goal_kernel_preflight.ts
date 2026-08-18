import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";


async function main(): Promise<void> {
	const [primeRoot, evidenceRoot, rawBudget, rookFullRoot] = process.argv.slice(2);
	const budget = Number(rawBudget);
	if (!primeRoot || !evidenceRoot || !rookFullRoot || !Number.isSafeInteger(budget) || budget <= 0) {
		throw new Error("usage: prime_goal_kernel_preflight <prime-root> <evidence-root> <token-budget> <rook-full-root>");
	}
	mkdirSync(evidenceRoot, { recursive: true });

	const ipythonUrl = pathToFileURL(
		join(primeRoot, "packages/coding-agent/src/core/tools/ipython.ts"),
	).href;
	const { IpythonKernelProvisioner } = await import(ipythonUrl);
	const goalRoot = join(primeRoot, "packages/coding-agent/skills/goal");
	const requests: string[] = [];
	let status = "active";
	const provisioner = new IpythonKernelProvisioner(evidenceRoot, {
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
		hostHandlers: {
			"goal.get": async () => {
				requests.push("goal.get");
				return {
					goal: {
						objective: "disposable campaign preflight",
						status,
						token_budget: budget,
						tokens_used: 0,
					},
					remaining_tokens: budget,
					completion_budget_report: null,
				};
			},
			"goal.complete": async () => {
				requests.push("goal.complete");
				status = "complete";
				return {
					goal: {
						objective: "disposable campaign preflight",
						status,
						token_budget: budget,
						tokens_used: 0,
					},
					remaining_tokens: budget,
					completion_budget_report: "preflight complete",
				};
			},
		},
	});

	let record: Record<string, unknown> | undefined;
	try {
		const manager = await provisioner.ensure();
		const execution = await manager.execute(`
import json
import sys
import goal as _goal_module
import rlm as _rlm_module
import rook_full as _rook_full_module
_goal_preimported = "goal" in globals()
_before = await _goal_module.get()
_after = await _goal_module.complete()
print(json.dumps({
    "pythonExecutable": sys.executable,
    "goalFile": _goal_module.__file__,
    "rlmFile": _rlm_module.__file__,
    "rookFullFile": _rook_full_module.__file__,
    "goalPreimported": _goal_preimported,
    "getStatus": _before["goal"]["status"],
    "getTokenBudget": _before["goal"]["token_budget"],
    "completeStatus": _after["goal"]["status"],
}, sort_keys=True))
`);
		if (execution.status !== "ok") {
			throw new Error(`preflight_kernel_execution_${execution.status}`);
		}
		const lines = execution.stdout.trim().split(/\r?\n/);
		const kernelRecord = JSON.parse(lines.at(-1) ?? "null");
		record = {
			schema: "rook.experiment.prime_goal_preflight:v2",
			...kernelRecord,
			requests,
			kernelClosed: false,
		};
	} finally {
		await provisioner.dispose();
	}
	if (!record) throw new Error("preflight_record_missing");
	record.kernelClosed = true;
	process.stdout.write(`${JSON.stringify(record)}\n`);
}


main().catch((error: unknown) => {
	process.stderr.write(`${error instanceof Error ? error.stack ?? error.message : String(error)}\n`);
	process.exitCode = 1;
});
