# Script Reference Collection

Reference repos for writing Rook's agent-optimized script library.
These are **not** direct dependencies — they're studied as reference
implementations to inform our own scripts with proper metadata headers,
adaptation points, and semantic naming.

## Repos

| Directory | Source | Stars | What to study |
|-----------|--------|-------|---------------|
| `rhino-developer-samples/` | [mcneel/rhino-developer-samples](https://github.com/mcneel/rhino-developer-samples) | 747 | Official API usage patterns, C#/Python/C++ |
| `rhinoscriptsyntax/` | [mcneel/rhinoscriptsyntax](https://github.com/mcneel/rhinoscriptsyntax) | 255 | The rhinoscriptsyntax source — understand what the high-level API wraps |
| `rhino-secrets/` | [runxel/rhino-secrets](https://github.com/runxel/rhino-secrets) | 54 | Tips, tricks, undocumented features |
| `rhinopython/` | [CADacombs/rhinopython](https://github.com/CADacombs/rhinopython) | 38 | Community Python scripts — real-world utility patterns |
| `rhinoScripts/` | [kleerkoat/rhinoScripts](https://github.com/kleerkoat/rhinoScripts) | 25 | Collected VBScript/Python scripts |
| `RhinoPythonScripts/` | [DarrelRonald/RhinoPythonScripts](https://github.com/DarrelRonald/RhinoPythonScripts) | 11 | Learning-oriented scripts |
| `RhinoScriptSamples/` | [scotttd/RhinoScriptSamples](https://github.com/scotttd/RhinoScriptSamples) | 7 | Plethora of VBScript samples |
| `rhino-scripts/` | [arnaudjuracek/rhino-scripts](https://github.com/arnaudjuracek/rhino-scripts) | 3 | Python utilities for Rhino |
| `grasshopper-examples/` | [runxel/grasshopper-examples](https://github.com/runxel/grasshopper-examples) | — | GH examples with VB.NET, C#, Python |

## How to use these

When writing a Rook script (e.g., `extract_layers.py`):

1. Search these repos for prior art: `grep -r "layer" --include="*.py" */`
2. Study the API calls and patterns used
3. Write our version with:
   - Metadata header (name, type, domain, purpose, used-by, adapt-points)
   - Semantic variable names (for Claude as primary reader)
   - `# ADAPT:` markers on context-sensitive sections
   - Structured JSON output
   - Modular functions that can be swapped individually

See `rook_docs/2026-04-10-public-skills-brainstorm.md` § "Infrastructure: Script Library"
for the full architecture.
