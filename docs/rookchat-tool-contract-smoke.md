# RookChat Tool Contract Smoke Checks

These checks are manual/provider probes, not CI gates. They are for comparing
model behavior after deterministic schema/dispatcher contract tests pass.

## Required local setup

From `C:\UDEV\Rook`:

```powershell
scripts\deploy-local-testing.ps1 -UseRepoVenv
```

Open Rhino, open Grasshopper, open the Rook Chat panel, and select the target
model in the panel.

## Required one-box prompt

```text
Create a Grasshopper C# script component that outputs one box. After creating it, check the canvas for errors and fix the existing component if needed. Report what you created and the exact error-check result.
```

## Expected successful sequence

- The model calls `request_tools` with `group: gh_canvas` at most once.
- The model calls `gh_create_csharp_script`, or `gh_create_script` with `language: csharp`.
- The script creation call includes `code`.
- For the alias tools, the call includes `pins_in` and `pins_out`.
- The C# code is RhinoCode C# Script body-style code, not a `GH_Component` subclass.
- The model calls `gh_errors`.
- Final response reports the created component and the exact error/warning result.

## Provider notes

- `ollama_chat/qwen3:14b`: current local smoke baseline.
- One cloud model: sanity comparison for tool contract regressions.
- Experimental local models such as Gemma variants are exploratory only and are not merge gates.

## Failure classification

- Schema/contract bug: model-visible schema permits arguments the dispatcher rejects.
- Dispatcher bug: model-visible schema requires or permits a valid field, but dispatch rejects it unexpectedly.
- Model behavior: schema is correct and dispatcher feedback is actionable, but the model ignores it.
- UI feedback bug: tool result succeeds/fails but the panel card misrepresents status.

Do not tune prompts or weaken schemas to make a single weak model pass. Fix
contract bugs first, then compare model behavior.
