# Grasshopper Connection Selector Correction Plan

> **For agentic workers:** Execute this compact plan inline with test-driven development. Do not broaden it into a route or framework redesign.

**Goal:** Make `/gh/connect` and `/gh/disconnect` resolve requested Grasshopper ports exactly, reject ambiguous or invalid selectors before mutation, and expose indexed connection selectors through `gh_connect`.

**Architecture:** Add one Rook-managed selector parser/resolver shared by the connect and disconnect handlers. It accepts explicit string names, explicit integer indices, and numeric `sourceParam`/`targetParam` as the retained raw-route alias; it resolves against the actual Grasshopper parameter collection and returns the resolved name and index. The Python MCP layer only expands the existing `gh_connect` schema and continues forwarding the request unchanged.

**Tech Stack:** C#/.NET Framework managed companion, reflection over Grasshopper objects, Python 3.11, MCP schemas, xUnit, pytest.

## Constraints

- Do not modify native C++, route ownership, bridge transport, or unrelated Grasshopper lifecycle code.
- Reject a request that supplies both the name/legacy field and the explicit index field for the same side.
- Reject malformed, negative, or out-of-range indices and unknown or blank names.
- Permit an omitted selector only when the resolved side has exactly one parameter.
- Preserve numeric `sourceParam` and `targetParam` as legacy raw-route aliases.
- Parse and resolve the complete request before adding or removing any source.
- Return the actual resolved parameter name and zero-based index.

## Task 1: Pin the failing contract

**Files:**

- Modify: `mcp_server/tests/test_server_gh_knowledge_wrappers.py`
- Add: `src/Rook.Tests/Handlers/GrasshopperConnectionSelectorTests.cs`

- [x] Extend the MCP schema/forwarding tests for `sourceIndex` and `targetIndex`.
- [x] Add managed tests for explicit names, explicit indices, legacy numeric aliases, conflicts, invalid ranges, unknown names, singleton omission, and multi-port omission.
- [x] Run the focused tests and confirm they fail for the missing behavior.

## Task 2: Implement the narrow correction

**Files:**

- Modify: `src/Rook/Handlers/GrasshopperHandler.cs`
- Modify: `mcp_server/src/rook/server.py`

- [x] Add one shared request parser and one shared parameter resolver used by connect and disconnect.
- [x] Resolve both sides before mutation and use only the resolved objects for connect/disconnect.
- [x] Return resolved names and indices in both route responses.
- [x] Add integer `sourceIndex` and `targetIndex` properties to the existing `gh_connect` schema.

## Task 3: Verify and exercise the real route

- [x] Run the focused managed and Python tests.
- [x] Run the relevant managed test project and focused MCP regression file without deploying.
- [ ] Build and deploy through the repository local-testing workflow only after hosts are closed.
- [ ] In a disposable Grasshopper document, connect to indices 5, 6, and 7, verify the graph and response metadata, then verify disconnect parity and remove the fixture.
- [ ] Confirm no native C++ files changed and review the final diff for scope.
