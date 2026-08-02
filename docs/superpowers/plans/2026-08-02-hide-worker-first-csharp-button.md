# Hide Worker-First C# Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the experimental **Build C#** action from the shipped RookChat panel while preserving ordinary Chat behavior and the complete internal Worker-first capability.

**Architecture:** Remove the single `AgentChatTab` constructor registration that adds the secondary button. Invert the existing source-wiring regression so it proves the UI doorway is absent while the private Worker-first path and ordinary Send/Enter wiring remain present; make no other product change.

**Tech Stack:** C#/.NET Framework 4.8, Eto.Forms, xUnit source-wiring tests.

## Global Constraints

- Preserve `OnBuildCSharpMessage`, `SendWorkerFirstCSharpStreamingAsync`, the exact `worker_first_csharp_v1` HTTP mode and server branch, the application root, Planner/Worker harness, compiler, operator scripts, and their existing tests.
- Preserve ordinary Send and Enter behavior exactly.
- Add no feature flag, setting, replacement button, menu, command, refactor, route cleanup, deprecation system, rename, generalization, or new abstraction.
- Modify only `src/Rook/UI/Chat/AgentChatTab.cs` and `src/Rook.Tests/UI/Chat/RookChatPanelTests.cs` during implementation.
- Do not contact providers, Rhino, Grasshopper, or the Worker box.
- Follow `docs/superpowers/specs/2026-08-02-hide-worker-first-csharp-button-design.md`.

---

### Task 1: Hide the UI registration and preserve internal wiring

**Files:**
- Modify: `src/Rook/UI/Chat/AgentChatTab.cs:53`
- Test: `src/Rook.Tests/UI/Chat/RookChatPanelTests.cs:221-234`

**Interfaces:**
- Consumes: `AgentChatTab` constructor registration, private `OnBuildCSharpMessage(string)`, `AgentChatClient.SendWorkerFirstCSharpStreamingAsync(...)`, ordinary `OnSendMessage(string)`, and inherited `ChatTab` Send/Enter submission wiring.
- Produces: an `AgentChatTab` with no visible **Build C#** secondary action, while all internal Worker-first and ordinary Chat methods remain unchanged.

- [ ] **Step 1: Invert and rename the existing source-wiring regression**

Replace `AgentChatTab_BuildAction_UsesDedicatedNonStickyClientPath` with this exact test body:

```csharp
[Fact]
public void AgentChatTab_BuildAction_IsHiddenWhileInternalPathRemains()
{
    var chatTab = ReadSourceFile("src", "Rook", "UI", "Chat", "ChatTab.cs");
    var agentTab = ReadSourceFile("src", "Rook", "UI", "Chat", "AgentChatTab.cs");

    Assert.DoesNotContain("ConfigureSecondaryAction(\"Build C#\", OnBuildCSharpMessage)", agentTab);
    Assert.Contains("private Task OnBuildCSharpMessage", agentTab);
    Assert.Contains("_client.SendWorkerFirstCSharpStreamingAsync", agentTab);
    Assert.Contains("_client.SendMessageStreamingAsync", agentTab);
    Assert.Contains("SubmitInputAsync(OnSendMessage)", chatTab);
    Assert.Contains("SubmitInputAsync(action)", chatTab);
    Assert.Contains("OnSendClicked(s, e)", chatTab);
    Assert.DoesNotContain("executionMode", agentTab);
}
```

- [ ] **Step 2: Run the changed regression and verify behavioral RED**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~AgentChatTab_BuildAction_IsHiddenWhileInternalPathRemains" --verbosity minimal
```

Expected: FAIL at the new `Assert.DoesNotContain(...)` because the constructor still registers **Build C#**. The retained-method and ordinary Send/Enter assertions should not be the failure cause.

- [ ] **Step 3: Remove only the visible constructor registration**

In the `AgentChatTab` constructor, delete exactly:

```csharp
ConfigureSecondaryAction("Build C#", OnBuildCSharpMessage);
```

Leave the adjacent `_client = new AgentChatClient();` and `BuildModelSelector();` statements unchanged. Do not edit `OnBuildCSharpMessage`, the client methods, `ChatTab`, or any Python code.

- [ ] **Step 4: Run the changed regression and verify GREEN**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~AgentChatTab_BuildAction_IsHiddenWhileInternalPathRemains" --verbosity minimal
```

Expected: PASS.

- [ ] **Step 5: Run the complete focused managed UI seam**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~RookChatPanelTests" --verbosity minimal
```

Expected: all 32 focused tests pass with zero failures. Existing compiler/analyzer warnings may remain unchanged.

- [ ] **Step 6: Audit the exact implementation scope and preserved symbols**

Run:

```powershell
git diff --check
git diff --name-only
rg -n 'ConfigureSecondaryAction\("Build C#"|OnBuildCSharpMessage|SendWorkerFirstCSharpStreamingAsync|SendMessageStreamingAsync' src/Rook/UI/Chat/AgentChatTab.cs
```

Expected:

- `git diff --check` reports no errors;
- the only uncommitted files are `src/Rook/UI/Chat/AgentChatTab.cs` and `src/Rook.Tests/UI/Chat/RookChatPanelTests.cs`;
- the exact **Build C#** registration is absent; and
- `OnBuildCSharpMessage`, `SendWorkerFirstCSharpStreamingAsync`, and ordinary `SendMessageStreamingAsync` references remain.

- [ ] **Step 7: Commit the implementation and reconciled test**

```powershell
git add -- src/Rook/UI/Chat/AgentChatTab.cs src/Rook.Tests/UI/Chat/RookChatPanelTests.cs
git diff --cached --check
git commit -m "fix(chat): hide experimental Build C# action"
```

Stop for review. Do not deploy or run any live integration.
