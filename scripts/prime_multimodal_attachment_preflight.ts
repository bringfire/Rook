import { createHash } from "node:crypto";
import { mkdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

function sha256(bytes: Buffer): string {
	return createHash("sha256").update(bytes).digest("hex").toUpperCase();
}

async function main(): Promise<void> {
	const [primeRootValue, stateRootValue, firstImageValue, secondImageValue] = process.argv.slice(2);
	if (!primeRootValue || !stateRootValue || !firstImageValue || !secondImageValue) {
		throw new Error("usage: preflight <prime-root> <state-root> <image-1> <image-2>");
	}
	const primeRoot = resolve(primeRootValue);
	const stateRoot = resolve(stateRootValue);
	const imagePaths = [resolve(firstImageValue), resolve(secondImageValue)];
	mkdirSync(stateRoot, { recursive: true });

	const ipythonModule = await import(
		pathToFileURL(join(primeRoot, "packages/coding-agent/src/core/tools/ipython.ts")).href
	);
	const packagePath = join(
		primeRoot,
		"packages/coding-agent/dist/skills/attach-image",
	);
	const provisioner = new ipythonModule.IpythonKernelProvisioner(stateRoot, {
		pythonSkills: [
			{
				name: "attach-image",
				importName: "attach_image",
				packagePath,
				pyprojectPath: join(packagePath, "pyproject.toml"),
			},
		],
		hostHandlers: {
			"model.info": async () => ({
				id: "ollama_chat/qwen3.8:27b",
				input: ["text", "image"],
			}),
		},
	});
	const code = `print(await attach_image(${JSON.stringify(imagePaths[0].replaceAll("\\", "/"))}, ${JSON.stringify(imagePaths[1].replaceAll("\\", "/"))}))`;
	try {
		const manager = await provisioner.ensure();
		const result = await manager.execute(code);
		if (result.status !== "ok") {
			throw new Error(`attachment execution failed: ${result.stderr}`);
		}
		if (!result.stdout.includes("Loaded 2 image(s) into context")) {
			throw new Error("attachment confirmation missing");
		}
		if (!result.attachments || result.attachments.length !== 2) {
			throw new Error("attachment count mismatch");
		}
		const attachments = result.attachments.map((attachment, index) => {
			const bytes = Buffer.from(attachment.data, "base64");
			return {
				index: index + 1,
				path: attachment.path?.replaceAll("\\", "/") ?? null,
				mimeType: attachment.mimeType,
				bytes: bytes.length,
				sha256: sha256(bytes),
			};
		});
		console.log(
			JSON.stringify({
				schema: "rook.experiment.prime_multimodal_attachment_preflight:v1",
				status: "pass",
				modelContact: false,
				rookContact: false,
				attachmentCode: code,
				sourceImages: imagePaths.map((path) => {
					const bytes = readFileSync(path);
					return { path: path.replaceAll("\\", "/"), bytes: bytes.length, sha256: sha256(bytes) };
				}),
				attachments,
			}),
		);
	} finally {
		await provisioner.dispose();
	}
}

void main().catch((error: unknown) => {
	console.error(error instanceof Error ? error.stack ?? error.message : String(error));
	process.exitCode = 1;
});
