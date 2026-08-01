#!/usr/bin/env bash
# Rook Plugin — SessionStart hook
# Re-injects skill cascade awareness after compaction or new session start.
# Follows the same pattern as Engram's build-blueprint-reminder.sh

set -euo pipefail

escape_for_json() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\n'/\\n}"
    s="${s//$'\r'/\\r}"
    s="${s//$'\t'/\\t}"
    printf '%s' "$s"
}

context="Chirp component categories are available: planner, interpreter, critic, narrator, classifier, gate, editor. When creating Chirp components, use the /chirp skill for single components or /chirp-cascade for multi-component workflows. The chirp_create MCP tool REQUIRES a category parameter. Correction input pin and Reasoning output pin are auto-added to all components — do NOT include them in pins_in/pins_out.

When the user asks to BUILD, CREATE, or DESIGN a complex Grasshopper definition (4+ components), use the /design-grasshopper skill cascade. This starts a 4-phase workflow: design \u2192 plan \u2192 execute \u2192 consolidate. For simple definitions (1-3 components), inspect with gh_snapshot, resolve exact components with gh_library or gh_knowledge_query, apply one bounded gh_edit batch, and verify with a follow-up snapshot.

Other skills: /consolidate (knowledge consolidation), /twisted-column (parametric columns)."

escaped=$(escape_for_json "$context")

echo "rook-session-start hook fired" >&2

cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "<EXTREMELY_IMPORTANT>\n${escaped}\n</EXTREMELY_IMPORTANT>"
  }
}
EOF
