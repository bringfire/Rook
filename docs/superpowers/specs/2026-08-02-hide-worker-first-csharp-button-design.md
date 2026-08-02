# Hide Worker-First C# Button Design

## Goal

Remove the experimental **Build C#** action from the shipped RookChat panel while preserving the proven internal Worker-first capability for operator-driven development.

## Change

Delete only this constructor registration from `AgentChatTab`:

```csharp
ConfigureSecondaryAction("Build C#", OnBuildCSharpMessage);
```

Without that registration, the inherited `ChatTab` layout remains the ordinary Send/Stop/Clear row. Send and Enter continue to invoke `OnSendMessage` unchanged.

Preserve `OnBuildCSharpMessage`, `SendWorkerFirstCSharpStreamingAsync`, the `worker_first_csharp_v1` HTTP mode and server branch, the application root, Planner/Worker harness, compiler, operator scripts, and their existing tests. Add no replacement surface, flag, setting, refactor, or cleanup.

## Verification

Invert and rename the existing narrow source-wiring regression to prove:

- `AgentChatTab` no longer registers the **Build C#** secondary action;
- the private Worker-first client path remains present; and
- ordinary Send and Enter wiring remains unchanged.

Run the focused managed RookChat panel tests. No provider, Worker, Rhino, or Grasshopper contact is permitted.

## File Scope

- `src/Rook/UI/Chat/AgentChatTab.cs`
- `src/Rook.Tests/UI/Chat/RookChatPanelTests.cs`

The implementation plan is one task: update the regression, remove the constructor registration, and verify the focused managed seam.
