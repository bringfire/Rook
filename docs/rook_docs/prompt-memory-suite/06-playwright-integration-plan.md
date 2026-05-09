# Playwright Integration Plan (Rhino Panel UI)

## Key principle
Use Playwright for embedded panel web UI behavior; use Rhino harness for host/runtime lifecycle.

## Existing foundation
- Owned Rhino runtime harness is shipped.
- Harness already scopes env and captures artifacts.

## Plan
1. Add new harness smoke mode: `playwright-panel`.
2. Add Playwright runner script that consumes `ROOK_RHINO_PORT` / `ROOK_RHINO_PROCESS_ID`.
3. Add `ROOK_HARNESS_ARTIFACT_DIR` to harness smoke env.
4. Add first smoke test for panel readiness.
5. Store Playwright report/trace/screenshots in harness run folder.

## Test split
- Playwright: palette/search/keyboard/pin UX.
- Rhino integration: panel open/focus/doc-scoped behavior.

## CI model
Windows self-hosted lane with Rhino installed.
