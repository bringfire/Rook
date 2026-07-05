# Rook 2.0 — v0.1 Hermes Plugin Validation (Evidence)

- **Date:** 2026-07-04 · **Result: FULL LADDER GREEN**
- **4-tuple:** plugin `44696ef` (rook-hermes-plugin v0.1.0) × Hermes v0.18.0 (upstream `19d41744`) × installed Rook release (`%LOCALAPPDATA%\Rook`, lean profile) × brain **GPT-5.5** (openai-codex provider)
- **Setup:** new-user simulation — config rewired from dev checkout to installed venv + `ROOK_MCP_TOOL_PROFILE=lean`, `plugins.enabled: [rook]`; plugin via junction (content-identical to clone).

## Ladder results (all pass)

1. `/rook` — discovered BOTH listeners in one Rhino process (native pid 77868 :64183, roadcreator :60899), both `[listening]`. Plugin load + discovery + port probe proven, zero tokens.
2. Ping + lean surface — `mcp_rook_rhino_ping` → pong; lean tool count confirmed.
3. Sphere round-trip — geometry appeared in viewport (full dispatch path).
4. GH snapshot → epoch returned (P/Invoke → C# companion seam).
5. `/rook setup` → flat-tree install; fresh session showed `rook/grasshopper` ambient.
6. Disciplined GH build observed (skill-guided snapshot→edit workflow).

## Significance

- First validated **cross-vendor** drive of Rook: non-Claude harness (Hermes) + non-Claude model (GPT-5.5) through the plugin + lean MCP surface.
- New-user path is real end-to-end: rook-release installer + hermes installer + `hermes plugins install` + `hermes mcp add` + `/rook setup`.
- Go-public gate for the plugin repo is satisfied (first green support-matrix row).

Spec: `docs/superpowers/specs/2026-07-03-rook-2.0-minimal-iteration-design.md` (§7 Phase 0/1, §11 topology). Correction-nudge hook: pending organic trigger (not force-tested).
