# Prime Agent Readonly Qualification Milestone

- Prime Agent commit: `c98941a2`.
- Model: `ollama/qwen3.6:35b` through the isolated loopback Ollama configuration.
- Frozen row: `C:/Users/bring/AppData/Local/Temp/prime-rook-readonly-qualification-v2/operator/row.json`; SHA-256 `782F1FDEAB96565E874C2F55C3B0E8F3C10220A1D2AA37418D1C3A40ED28C30B`.
- Prime JSONL: `C:/Users/bring/AppData/Local/Temp/prime-rook-readonly-qualification-v2/operator/prime.jsonl`; SHA-256 `E2CEFAF56FE7A6C92D1BBCB5B00859260E2D72DC783593E72E9FFFA86F9E9983`.
- Native Prime session: `C:/Users/bring/AppData/Local/Temp/prime-rook-readonly-qualification-v2/agent/sessions/019fd512-9e31-734a-a8b2-914f81e6cb09.jsonl`; SHA-256 `DEF8A4ECFADD6B2D0607D51F02581F6B232629655C73CF0A55A41A79CC2C6C8E`.
- Stderr was empty. The original failed qualification evidence remains unchanged in its sibling directory.

## Successful Transaction

The local model loaded the reviewed Rook skill and then followed the focused canonical gateway sequence exactly:

```text
rook_tools_search(query="gh_snapshot")
-> rook_tools_read(name="gh_snapshot")
-> rook_tools_call(name="gh_snapshot", arguments={...})
-> final report
```

The session contained four IPython calls: skill load, search, read, and call. It performed exactly one `gh_snapshot`, no `list_tools`, direct tool invocation, mutation, retry, targeting workaround, or adapter bypass. The readonly snapshot returned an unnamed unsaved canvas at epoch `3` with zero components, wires, errors, and warnings. No qualification-owned subprocess remained after Prime exited.

Qwen's final response incorrectly inferred document history from the empty canvas and epoch: current snapshot state does not establish whether edits previously occurred. This bounded model-quality error does not invalidate the gateway qualification.

## Proven Claims And Non-Claims

For this supervised specimen, a local model running inside Prime Agent can load an explicit reviewed skill, discover and read one Rook capability without exposing the full catalog, invoke that capability through Rook's canonical MCP gateway, and interpret the authentic readonly result. Rook's readonly authority boundary remained effective.

This does not prove mutation, automatic skill selection, arbitrary-intent competence, repeatability, recursion or delegation, OS-level isolation, or superiority over another agent runtime. It does not fix ChatRunner's fallback-catalog defect; Prime avoided that surface by consuming canonical live MCP schemas. Prime exit `0` proves only normal agent lifecycle termination. No correlated supplemental Rook record was located, so the retained Prime session and returned MCP result are the primary call-count evidence.

The readonly qualification stops here. The next useful experiment is one separately reviewed and authorized sibling qualification on a fresh disposable canvas, reusing the same adapter with Rook's reviewed Grasshopper execution skill, one supervised mutation task, and one final evidence snapshot. This result justifies no Rook or Prime code changes.
