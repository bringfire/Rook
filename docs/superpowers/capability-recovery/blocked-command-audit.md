# Blocked Command Audit

Status: Phase-one assessment

This audit records where raw command fallback pressure exists after `/command` lockdown. Historical frequency is a weighting signal, not the definition of capability coverage.

| Source | Observed or likely command fallback | Current safety outcome | Typed recovery candidate | Risk class | Follow-up |
| --- | --- | --- | --- | --- | --- |
| MCP `rhino_command` | `_Line`, `_Circle`, `_Box`, other creation commands | rejected unless known safe metadata exists | `rhino_create` | good refusal if advisory names `rhino_create`; bad refusal if no route is discoverable | Add minimal candidate advisory for obvious create commands. |
| MCP `rhino_command` | `_SelNone`, `_SelAll`, `_Sel*` | rejected unless explicitly safe | `rhino_select_none`, `rhino_select`, `rhino_select_by_type` | good refusal when selection route is obvious | Ensure docs/evals teach selection tools. |
| SmartExecutor known-command fallback | stalled command fallback attempts | interactive execution is deprecated/refused | typed route or explicit manual boundary | good refusal | Keep deprecated prompt-driving path out of normal execution. |
| Native `/command` | prompt-inducing commands such as `_Line` without points | fails closed and can quarantine | typed tool with explicit parameters | good refusal | Covered by live RunScript safety smoke. |
| Native `/command` | bare no-effect commands | fail-closed unless explicitly allowlisted | typed route or manual boundary | intentional breaking behavior | Document as compatibility break. |
| Agent behavior | future models reaching for raw commands despite typed tools | refusal expected | stronger tool descriptions and candidate advisories | weak refusal if typed route exists but is hard to discover | Synthetic evals should measure route choice. |
| Formatter/envelope transport | MCP `call_tool` wraps failures as `Error: <json>` text | structured fields are available but not raw JSON transport | parse trailing JSON or future formatter contract | follow-up infrastructure | Queue as phase-two contract cleanup, not phase-one blocker. |
