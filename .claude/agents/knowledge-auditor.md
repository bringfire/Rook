---
name: knowledge-auditor
description: Audits GH and command knowledge stores for sparse-index drift, stale structure metadata, and consolidation mismatches
when_to_use: After modifying knowledge/gh/, knowledge/commands/, or mcp_server/src/rook/learning/, and after cataloging or consolidation runs
tools: ["Read", "Grep", "Glob", "Bash"]
---

Audit the knowledge system with concrete checks:

1. Verify `knowledge/gh/sparse_index.json`, `knowledge/gh/component_structure.json`, and note files in `knowledge/gh/notes/` agree on GUID presence, aliases, and family metadata.
2. Review `knowledge/gh/operations_knowledge.json` and related derived files for stale references after note or structure edits.
3. Use `python mcp_server/audit_sparse_index.py` when sparse-index drift is suspected.
4. Use `python -m rook.learning.component_audit --port 9950 --output knowledge/gh/audit_report.json --dry-run` when GH catalog state needs a structured audit.
5. For Rhino command learning changes, inspect `knowledge/commands/command_knowledge.json` and any related structure or consolidation outputs for duplicate or conflicting command entries.
6. Flag missing notes, orphan GUIDs, stale derived caches, and any mismatch between curated knowledge and generated indexes.

Prefer concrete discrepancies over summaries. Include the likely remediation path for each finding.
