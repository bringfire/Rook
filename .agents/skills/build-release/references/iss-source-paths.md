# Inno Setup Source Path Checklist

Every file listed here is referenced by `installer/RookSetup.iss`. If any file
is missing, ISCC will either fail or silently exclude the component (if
`skipifsourcedoesntexist` is set).

All paths are relative to the repo root.

## Build Outputs (must be fresh — rebuilt after version bump)

| File | Source |
|------|--------|
| `src/RookNative/bin/Release/x64/RookNative.rhp` | C++ build output |
| `src/RookNative/bin/Release/x64/RookNative.pdb` | C++ debug symbols |
| `src/Rook/bin/x64/Release/net48/Rook.rhp` | C# build output |
| `src/Rook/bin/x64/Release/net48/Rook.rui` | Rhino toolbar file |
| `src/Rook/bin/x64/Release/net48/*.dll` | C# dependency DLLs (expect ~9) |

**CRITICAL:** The C# companion builds to `bin/x64/Release/net48/` when using
`/p:Platform=x64`. The .iss `CompanionDir` must reference this path, NOT
`bin/Release/net48/` (which is the output without the Platform flag).

## Python MCP Server

| File/Dir | Notes |
|----------|-------|
| `mcp_server/pyproject.toml` | Package definition |
| `mcp_server/README.md` | Package readme |
| `mcp_server/src/rook/` | Full source tree (recursesubdirs) |

## Chirp Adapter (sibling repo)

| File/Dir | Notes |
|----------|-------|
| `../Chirp/pyproject.toml` | Chirp package definition |
| `../Chirp/src/chirp/` | Chirp source tree (recursesubdirs) |

The .iss references `ChirpDir = RepoRoot + "\..\Chirp"`. This is a sibling repo
at the same directory level as Rook.

## Knowledge Stores

| Dir | Notes |
|-----|-------|
| `knowledge/commands/` | Must be non-empty (196+ Rhino command files) |
| `knowledge/gh/` | Must be non-empty; excludes `sessions/` subdir |

## Claude / Codex Agent Assets

| File/Dir | Notes |
|----------|-------|
| `.claude-plugin/plugin.json` | Plugin manifest |
| `.claude-plugin/marketplace.json` | Marketplace registration |
| `.claude/skills/` | Claude Code skill payload (recursesubdirs) |
| `.claude/agents/` | Claude agent payload (recursesubdirs) |
| `.agents/skills/` | Codex skill payload (recursesubdirs) |
| `hooks/hooks.json` | Hook definitions |
| `scripts/session-start.sh` | Session startup script |

## Installer Assets

| File | Notes |
|------|-------|
| `installer/post_install.py` | Post-install automation |
| `installer/rook-icon.ico` | Application icon |
| `installer/pre-install-readme.txt` | Pre-install information |
| `installer/CLAUDE.md` | Installed Claude instruction file |
| `installer/AGENTS.md` | Installed Codex instruction file |

## Agent-Facing Documentation

These are installed to `{localappdata}\Rook\docs\` and referenced by the
installed CLAUDE.md.

| File | Notes |
|------|-------|
| `docs/ONBOARDING_NEW_CLAUDE.md` | Quick decision tree for tool selection |
| `docs/CURRENT_ARCHITECTURE.md` | Runtime architecture description |
| `docs/AGENT_ARCHITECTURE.md` | Agent system, intent runtime, chat service |
| `docs/TROUBLESHOOTING.md` | Common issues and recovery |

## User Documentation

| File | Notes |
|------|-------|
| `QUICK_START.md` | User quick start guide |
| `AGENT_SETUP.md` | Agent setup guide |
| `BUILDING.md` | Build and source-install guide |
| `LICENSE` | License file |

## Verification Script

Run this to check all paths at once:

```bash
REPO="<your-rook-repo-path>"
MISSING=0

for f in \
  "$REPO/src/RookNative/bin/Release/x64/RookNative.rhp" \
  "$REPO/src/RookNative/bin/Release/x64/RookNative.pdb" \
  "$REPO/src/Rook/bin/x64/Release/net48/Rook.rhp" \
  "$REPO/src/Rook/bin/x64/Release/net48/Rook.rui" \
  "$REPO/mcp_server/pyproject.toml" \
  "$REPO/../Chirp/pyproject.toml" \
  "$REPO/.claude-plugin/plugin.json" \
  "$REPO/.claude-plugin/marketplace.json" \
  "$REPO/hooks/hooks.json" \
  "$REPO/scripts/session-start.sh" \
  "$REPO/installer/post_install.py" \
  "$REPO/installer/rook-icon.ico" \
  "$REPO/installer/pre-install-readme.txt" \
  "$REPO/installer/CLAUDE.md" \
  "$REPO/installer/AGENTS.md" \
  "$REPO/mcp_server/README.md" \
  "$REPO/docs/ONBOARDING_NEW_CLAUDE.md" \
  "$REPO/docs/CURRENT_ARCHITECTURE.md" \
  "$REPO/docs/AGENT_ARCHITECTURE.md" \
  "$REPO/docs/TROUBLESHOOTING.md" \
  "$REPO/QUICK_START.md" \
  "$REPO/AGENT_SETUP.md" \
  "$REPO/BUILDING.md" \
  "$REPO/LICENSE"
do
  if [ ! -e "$f" ]; then
    echo "MISSING: $f"
    MISSING=$((MISSING + 1))
  fi
done

# Check directories are non-empty
for d in \
  "$REPO/mcp_server/src/rook" \
  "$REPO/../Chirp/src/chirp" \
  "$REPO/knowledge/commands" \
  "$REPO/knowledge/gh" \
  "$REPO/.claude/skills" \
  "$REPO/.claude/agents" \
  "$REPO/.agents/skills"
do
  if [ ! -d "$d" ] || [ -z "$(ls -A "$d" 2>/dev/null)" ]; then
    echo "MISSING OR EMPTY: $d"
    MISSING=$((MISSING + 1))
  fi
done

# Check C# DLLs exist
DLL_COUNT=$(ls "$REPO/src/Rook/bin/x64/Release/net48/"*.dll 2>/dev/null | wc -l)
if [ "$DLL_COUNT" -lt 1 ]; then
  echo "MISSING: C# dependency DLLs"
  MISSING=$((MISSING + 1))
fi

echo ""
if [ "$MISSING" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
else
  echo "FAILED: $MISSING items missing"
fi
```
