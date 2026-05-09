# Mock Fixtures Reference

## Suggested fixture set
- `prompts-recent.json`
- `prompts-frequent.json`
- `prompts-search.json`
- `prompt-details.json`
- `prompt-lineage.json`
- `upsert-response-created.json`
- `upsert-response-deduped.json`
- `use-response.json`
- `outcome-response.json`
- `pin-response.json`
- `delete-response.json`
- `session-settings-response.json`
- `error-invalid-argument.json`
- `error-not-found.json`
- `error-rate-limited.json`

## Mock router behavior
- route by method + path
- deterministic fixture return
- `/prompts/upsert` can return created or deduped fixture via simple text heuristic

## Output policy
All mock outputs should preserve the unified envelope:
- `ok`
- `data`
- `error`
- `request_id`
