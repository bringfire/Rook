# Implementation Checklist

## Code changes
- [ ] `scripts/run_rhino_runtime_harness.py`
  - [ ] add `playwright-panel` smoke choice
  - [ ] map command to `scripts/run_playwright_panel_smoke.ps1`
- [ ] `mcp_server/src/rook/runtime_harness.py`
  - [ ] inject `ROOK_HARNESS_ARTIFACT_DIR` into smoke env
- [ ] `scripts/run_playwright_panel_smoke.ps1` (new)
  - [ ] validate required env vars
  - [ ] run Playwright
  - [ ] emit artifacts to harness dir
- [ ] `ui_tests/playwright/playwright.config.ts` (new)
- [ ] `ui_tests/playwright/panel-smoke.spec.ts` (new)
- [ ] docs update in `BUILDING.md`

## Acceptance
- [ ] `--smoke playwright-panel` runs end-to-end
- [ ] artifacts appear under `.scratch/rhino-runtime-harness/<run-id>/playwright-*`
- [ ] nonzero Playwright exit marks harness non-green
- [ ] existing smoke modes unaffected
