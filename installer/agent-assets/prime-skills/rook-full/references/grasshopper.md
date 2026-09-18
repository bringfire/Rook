# Grasshopper Guidance

Document-independent catalog and component-library queries do not require an
active canvas. Document-scoped observations report the canonical active
Grasshopper document identity. Use that value as `expectedGhDocumentId` for a
later guarded mutation when its advertised schema requires it.

At managed callback entry, Rook captures the active canvas and document once,
compares the expected identity, and executes the operation against the same captured document.
If the active document changed, observe again before deciding
whether to continue.

Explicit transitions such as `gh_document_open` and document creation do not
require an expected document identity; observe the resulting active document
before dependent work. Rich authoring tools remain available, including
`gh_update_script` and other typed script-component operations. Target custody
governs Rook's typed dispatch and is not a sandbox for authored code.

Prefer local, attributable repairs. Preserve useful components and wiring where
practical, inspect diagnostics after solving, and distinguish temporary control
changes from the final intended definition.
