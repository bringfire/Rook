Task 3 Report: LM8I Publication Support Packet Wiring

Date: 2026-07-09
Workspace: C:/UDEV/Rook

Summary
- Added `_publication_support_knowledge_packet(...)` to convert the bounded support context into a `WorkerKnowledgePacket`.
- Updated `_build_local_turn_payload(...)` to accept an optional `publication_support_context` and append the support packet only when provided.
- Added regression coverage ensuring the support packet is present without changing the allowed action set.

TDD Evidence
1. Red
   - Ran:
     `.\\mcp_server\\.venv\\Scripts\\python.exe -m pytest mcp_server\\tests\\test_lm8i_affine_publication_shape_support_probe.py -q`
   - Result:
     one new test failed with `NameError: name '_valid_affine_fixture' is not defined`, which showed the regression test needed to use the existing fixture path in this file.
2. Green
   - Re-ran the same focused test module after fixing the test to build the graph from the existing fake-tool affine fixture.
   - Result:
     `16 passed in 0.21s`

What Changed
- `scripts/lm8i_affine_publication_shape_support_probe.py`
  - Added `_publication_support_knowledge_packet(context: Mapping[str, Any]) -> WorkerKnowledgePacket`.
  - Validates the incoming context packet id and fields mapping before constructing the packet.
  - Keeps the support packet content bounded to the fields already produced by `_publication_support_context(...)`.
  - Extended `_build_local_turn_payload(...)` with `publication_support_context: Mapping[str, Any] | None = None`.
  - Builds the knowledge packets explicitly so the original evidence packet remains unchanged and the support packet is appended only when present.

- `mcp_server/tests/test_lm8i_affine_publication_shape_support_probe.py`
  - Added a focused regression test that:
    - creates the affine graph from the existing fake fixture path
    - builds a publication support context from the skeletal `action_request` pass-1 row
    - verifies both knowledge packets are present
    - verifies the allowed action stays `draft_gh_set_value_params`
    - checks for the absence of authority leaks such as raw `3.0`, editable GUIDs, or standalone tool-call names in the support packet render

Boundary Notes
- I did not modify `_run_probe(...)` orchestration.
- I did not touch `scripts/lm_worker_two_pass_publication.py` or LM8H.
- I did not run live Rhino or Grasshopper.
- The support packet stays within the review clarification: it includes the required action id and procedural instruction, but not action input suggestions, hidden `3.0`, raw GUIDs, standalone GH tool call fields/names, topology/wiring/code/script authority, or batch authority.

Verification
- Ran:
  `.\\mcp_server\\.venv\\Scripts\\python.exe -m pytest mcp_server\\tests\\test_lm8i_affine_publication_shape_support_probe.py -q`
- Result:
  `16 passed in 0.21s`

Commit
- Planned commit message:
  `feat(lm8i): render publication support packet`

Concerns
- None.
