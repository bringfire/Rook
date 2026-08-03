# Compositional Harness Slice 2 Live Qualification Milestone

- Qualified merge SHA: `2081383447f07f4d7bd3d640876bfee34a12ca08` (PR #542).
- Result: `C:/Users/bring/AppData/Local/Rook/traces/semantic-graph-worker-leaf-20260803T231533.125147Z-p31152.json`.
- SHA-256: `594981013303E11FD004399ACFBDEEC89A8F9F86CB64D840A5D9B662BC4AA893`.
- Calls: one frontier Planner, one local Worker, one real `gh_create_csharp_script`, one `gh_snapshot`, one `gh_edit`, and one `gh_connect`; zero retries, repairs, updates, or fallbacks.

## Qualification Defects And Corrections

The first qualification reached the final connection but exposed that `ToolDispatcher` did not register the existing `POST /gh/connect` route. PR #540 added only that shared bridge registration and its dispatch-boundary regression.

The next qualification completed mechanically but connected C# output index `0`, which Grasshopper reserves for the built-in `out` text stream. It therefore did not prove the Planner-authored `A` edge. PR #542 captured the established physical convention in one compiler constant: declared C# outputs begin at index `1`. Causal tests now model `[out/0, A/1]` and reject `out/0` connection evidence.

## Successful Transaction

The Planner authored one unresolved C# node, one deterministic Construct Point node, and the semantic edge `A -> x`. The compiler partitioned the graph, the Worker authored the complete body `A = 7.0;`, and Grasshopper returned a clean C# create receipt. Deterministic execution then created the Construct Point region and the final real connection proved:

```text
05533763-2fd9-42ad-95b6-4df0d928c754 / A / output 1
->
b4e17f97-491e-49f9-a7ed-0d7c8f3f30e5 / X coordinate / input 0
```

The requested and returned endpoint GUIDs and indices matched. Both the Worker handoff and deterministic region ended at `terminal_node_selected:done`, and the aggregate returned `completed=true`.

## Proven Claims And Non-Claims

For this fixed specimen, Slice 2 proves that a Planner-authored semantic graph can be deterministically partitioned into one unresolved Worker leaf and one deterministic Grasshopper region; the existing Worker can fill only the admitted C# body; both regions can execute through their existing native receipt boundaries; and receipt-derived identities can connect the declared C# output to the intended deterministic input in one real transaction.

This does not prove runtime value correctness, broad intent coverage, variable C# interfaces, more than one Worker leaf, repeatability, retries or repair behavior, generalized scheduling, product-UI integration, knowledge retrieval, DSPy optimization, or semantic fidelity beyond the admitted structural edge. The retained JSON contains sensitive local diagnostic telemetry; it is neither canonical evidence nor an archive.

Slice 2 stops here. No rerun, additional harness logic, generalized Worker interface, or execution framework is warranted by this qualification. Any next slice must introduce and review a separate, explicitly bounded freedom.
