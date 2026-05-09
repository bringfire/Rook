# Prompt Memory Graph Contract v0

## Scope
Shared memory for humans + agents across Vision and Chat.

## Entities
- PromptRecord
- PromptVariantEdge (DERIVED_FROM)
- PromptUseEvent
- PromptOutcomeEvent

## PromptRecord (canonical fields)
- prompt_id
- text
- normalized_text
- source_surface, source_op
- author_type, author_id
- created_at_utc, last_used_at_utc
- use_count, is_pinned
- project_scope_kind, project_scope_id
- visibility_scope
- metadata (provider/model/tags)

## Required operations
- upsert_prompt
- record_use
- record_outcome
- create_variant
- pin/unpin
- soft_delete
- get_recent / get_frequent / search
- get_prompt_details / get_lineage

## Ranking v0
`score = text_match + recency + frequency + pin + context + outcome`

## Agent first-class rules
- Agent writes require stable agent_id/runtime/version.
- Agent prompts are provenance-labeled in UI.
- No in-place overwrite of human prompt text by agents.
- Rate limits + duplicate suppression on agent writes.

## Governance
- Scope enforcement (local/project/shared)
- Audit event trail
- Redaction hooks for secret-like inputs
