# Rook Troubleshooting Guide

> **DIRECTOR HISTORICAL EVIDENCE — classified 2026-07-13:** Director routes,
> tool names, and workflows below are retained only as dated evidence. They are not
> current instructions and must not be used to restore a Director MCP tool. See the
> [Director MCP Surface Retirement Design][director-mcp-retirement].

[director-mcp-retirement]: superpowers/specs/2026-07-13-director-mcp-surface-retirement-design.md

Solutions for common installation and runtime issues.

---

## Table of Contents

1. [Rhino Frozen / Not Responding](#rhino-frozen--not-responding)
2. [Installation Issues](#installation-issues)
3. [Connection Issues](#connection-issues)
4. [Claude Client Issues](#claude-client-issues)
5. [Rhino Plugin Issues](#rhino-plugin-issues)
6. [MCP Server Issues](#mcp-server-issues)
7. [Knowledge System Issues](#knowledge-system-issues)
8. [Diagnostic Commands](#diagnostic-commands)

---

## Rhino Frozen / Not Responding

This is the most common issue. Rhino uses a single UI thread — if a modal dialog is open, **all** HTTP requests block until it's dismissed.

### Symptoms
- `rhino_ping` times out
- All MCP tools hang
- Rhino's viewport stops responding to clicks

### Cause

A Rhino command prompted for input via a modal dialog box. This typically happens when:
- `rhino_command` or `rhino_execute` was used with incorrect syntax
- A script sent via `RunScript` had a syntax error (Rhino shows an error dialog that cannot be caught programmatically)
- A command is waiting for user input (e.g., "Select objects")

### Solution

1. **Switch to the Rhino window** — look for any dialog box, prompt, or command-line message
2. **Dismiss it** — click OK/Cancel, press Escape, or press Enter
3. **Verify recovery** — call `rhino_ping` (should return "pong")

### Prevention

- Rediscover the admitted Rhino tools, inspect document state, and prefer an explicit typed route
- Avoid `rhino_execute` and `rhino_command` with interactive UI paths
- If no typed route fits, query `knowledge_query(intent="...", depth="context")`, preflight a fully scripted command or short non-interactive script, and verify the host result

---

## Installation Issues

### uv fails to install

**Symptoms:**
- "ERROR: Failed to install uv"
- PowerShell execution policy errors

**Solutions:**

1. **Install uv manually via winget:**
   ```bash
   winget install --id=astral-sh.uv -e
   ```

2. **Install uv manually via scoop:**
   ```bash
   scoop install main/uv
   ```

3. **Install uv manually via PowerShell:**
   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install | iex"
   ```

4. **Check if uv is already installed:**
   ```bash
   uv --version
   ```

After manual installation, re-run the Rook installer.

---

### Virtual environment creation fails

**Symptoms:**
- "ERROR: Failed to create virtual environment"
- Python version errors

**Solutions:**

1. **Check network connection** - uv downloads Python automatically if needed

2. **Clear uv cache and retry:**
   ```bash
   uv cache clean
   ```
   Then re-run the Rook installer.

3. **Check disk space** - The virtual environment needs ~6GB

4. **Check folder permissions** - Ensure you have write access to the installation folder

---

### Dependencies fail to install

**Symptoms:**
- "ERROR: Failed to install dependencies"
- Package resolution errors

**Solutions:**

1. **Retry installation:**

   The managed runtime is at `%LOCALAPPDATA%\Rook\venv`. To reinstall dependencies:
   ```bash
   %LOCALAPPDATA%\Rook\venv\Scripts\python.exe -m pip install --force-reinstall rook-mcp
   ```

2. **Check for firewall/proxy issues** - uv needs to download packages from PyPI

3. **Update uv:**
   ```bash
   uv self update
   ```

---

## Connection Issues

### "Connection refused" errors

**Symptoms:**
- Claude reports connection refused
- MCP tools time out

**Causes & Solutions:**

1. **Rhino is not running**
   - Start Rhino 8
   - Wait for it to fully load (the native plugin auto-starts its HTTP server on load)

2. **Plugin didn't load**
   - In Rhino, type `PlugInManager`
   - Look for "RookNative" — it should show as loaded
   - If not found, see [Plugin not loading](#plugin-not-loading)

3. **Port discovery failed**
   - RookNative uses an OS-assigned port, discovered via `%LOCALAPPDATA%\Rook\discovery\` JSON files
   - Check that discovery files exist: `dir %LOCALAPPDATA%\Rook\discovery\`
   - Also check legacy diagnostics in `%TEMP%\rook\`
   - Restart Rhino to regenerate them

4. **Modal dialog blocking** — see [Rhino Frozen / Not Responding](#rhino-frozen--not-responding)

---

## Claude Client Issues

### "rook not found" in Claude

**Symptoms:**
- `/mcp` doesn't show rook
- Tools not available

**Solutions:**

1. **Restart Claude completely**
   - Close all Claude Code terminals
   - Close Claude Desktop
   - Reopen

2. **Verify configuration was created:**

   For Claude Code:
   ```bash
   claude mcp list
   ```
   Should show `rook`

   The installer writes Claude Code config to:
   ```
   ~/.claude.json
   ```

   For Claude Desktop, check:
   ```
   %APPDATA%\Claude\claude_desktop_config.json
   ```
   Should contain `rook` in `mcpServers`

3. **Re-run the Rook installer** from [GitHub Releases](https://github.com/bringfire/rook-release/releases)

4. **Manual configuration for Claude Code:**
   ```bash
   claude mcp add --scope user rook "%LOCALAPPDATA%\Rook\venv\Scripts\python.exe" -- -m rook
   ```

---

### MCP tools show errors in Claude

**Symptoms:**
- Tools appear but return errors
- "Module not found" errors

**Solutions:**

1. **Verify MCP server can load:**
   ```bash
   "%LOCALAPPDATA%\Rook\venv\Scripts\python.exe" -m rook
   ```
   Press Ctrl+C to exit. Should not show import errors.

2. **Check Python path in config:**
   - Must point to `%LOCALAPPDATA%\Rook\venv\Scripts\python.exe`
   - Path should use forward slashes: `C:/Users/...`

3. **Reinstall dependencies:**
   ```bash
   "%LOCALAPPDATA%\Rook\venv\Scripts\python.exe" -m pip install --force-reinstall rook-mcp
   ```

---

## Rhino Plugin Issues

### Plugin not loading

**Symptoms:**
- "RookNative" not in Plugin Manager
- MCP tools all fail

Rook has two plugins that work together:
- **RookNative.rhp** (C++) — the HTTP server, handles all Rhino geometry operations
- **Rook.rhp** (C#) — companion, handles Grasshopper operations and the chat panel

Both are deployed to the same directory. RookNative loads first and loads the companion on demand.

**Solutions:**

1. **Check plugin location:**
   ```
   %APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\
   ```
   Should contain both `RookNative.rhp` and `Rook.rhp`

2. **Re-run the Rook installer** to re-deploy the plugin files.

3. **Manually load plugin:**
   - In Rhino: `PlugInManager`
   - Click "Install..."
   - Navigate to the plugin folder
   - Select `RookNative.rhp`

4. **Check Rhino version:**
   - Rook requires Rhino 8
   - Check: `Help > About Rhinoceros`

---

### Plugin loads but HTTP server fails

**Symptoms:**
- RookNative appears in Plugin Manager
- `rhino_ping` times out
- No native discovery file in `%LOCALAPPDATA%\Rook\discovery\`

**Solutions:**

1. **Check for blocking firewall:**
   - Windows Defender may block localhost connections
   - Add exception for Rhino

2. **Check Rhino command line for error messages** — errors during HTTP server startup are logged there

3. **Restart Rhino** — the HTTP server starts automatically on plugin load

---

### Grasshopper tools fail but Rhino tools work

**Symptoms:**
- `rhino_ping` works, `gh_status` fails
- GH component creation fails

**Cause:** The C# companion plugin (which handles all GH operations) failed to load or its P/Invoke callback registration failed.

**Solutions:**

1. **Check both plugins are loaded** in `PlugInManager` — look for both "RookNative" and "Rook"
2. **Restart Rhino** — the companion is loaded on demand by the native plugin
3. **Open Grasshopper** — the companion initializes GH callbacks when Grasshopper is first opened

---

### Native handler behaves wrong / corrupt — but only on some builds

**Symptoms:**
- One native route misbehaves (reads a garbage request body, returns nonsense, hangs, or hard-crashes Rhino) while sibling routes in the *same* handler file work fine.
- The symptom **changes across rebuilds** of the same source — e.g. a size reads as `0` one build, `SIZE_MAX` the next, a crash the next.

**Likely cause when this pattern appears:** MSVC **incremental LTCG (Link-Time Code Generation)
nondeterminism**. (This was the *observed* cause in the 2026-06-24 incident below — treat it as the
first hypothesis to rule out, not a certainty for every corrupt native route.) The build keeps an
incremental codegen cache (`.iobj`/`.ipdb`) in `src/RookNative/bin/<Config>/x64/`. Wiping only the
front-end `obj/` does **not** clear it, so a stale or miscompiled function (most often a
large/complex one) gets carried forward. This presents exactly like an ABI / ODR / request-boundary
corruption bug and will waste hours if chased as one.

**Rule — do this BEFORE diagnosing ABI/ODR/request-corruption:** force a *fully* clean rebuild and
redeploy. Do **not** trust incremental-build behavior for this class of issue.

```powershell
# Wipe BOTH the front-end objs AND the LTCG cache (.iobj/.ipdb live in bin/)
Remove-Item -Recurse -Force "src\RookNative\obj\RookNative\Release" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "src\RookNative\bin\Release" -ErrorAction SilentlyContinue
.\build_native.ps1 -Configuration Release    # then deploy (Rhino must be closed)
```

A correct clean build logs `Previous IPDB not found, fall back to full compilation` /
`All NNNNN functions were compiled`. If the symptom vanishes after that, it was build
nondeterminism. (Reference incident: RookVisionDirector `/director/replay`, 2026-06-24 — full
write-up in `docs/superpowers/2026-06-24-replay-live-gate-postmortem.md`.)

---

## MCP Server Issues

### Server module fails to import

**Symptoms:**
- `import rook` fails
- Missing module errors

**Solutions:**

1. **Verify virtual environment:**
   ```bash
   "%LOCALAPPDATA%\Rook\venv\Scripts\python.exe" -c "import rook; print('OK')"
   ```

2. **Reinstall:**
   ```bash
   "%LOCALAPPDATA%\Rook\venv\Scripts\python.exe" -m pip install --force-reinstall rook-mcp
   ```

---

### Server runs but Rhino doesn't respond

**Symptoms:**
- MCP server starts
- `rhino_ping` times out

**Solutions:**

1. **Check Rhino is running and plugin is loaded**

2. **Check for modal dialogs in Rhino** — see [Rhino Frozen / Not Responding](#rhino-frozen--not-responding)

3. **Check discovery files exist:**
   ```bash
   dir %LOCALAPPDATA%\Rook\discovery\
   ```
   Should contain `instance-{PID}-native.json`. If missing, restart Rhino.

---

## Knowledge System Issues

### "Knowledge store not found" warning

**Symptoms:**
- Installer shows knowledge warning
- Explicit command/component workflows cannot load expected syntax, GUID, or gotcha guidance

**Solutions:**

1. **Verify knowledge directory exists:**
   ```
   knowledge/commands/command_knowledge.json
   ```

   The installer registers:
   - `ROOK_INSTALL_ROOT=%LOCALAPPDATA%\Rook\app`
   - `ROOK_DATA_DIR=%LOCALAPPDATA%\Rook\data`

2. **Re-run the installer** — the knowledge store may not have been extracted correctly

3. **Check path structure:**
   ```
   Rook/
   ├── mcp_server/
   └── knowledge/
       └── commands/
           └── command_knowledge.json
   ```

---

### Knowledge fails to load

**Symptoms:**
- "WARNING: Knowledge loading test failed"
- Intent-based commands fail

**Solutions:**

1. **Test loading manually:**
   ```bash
   "%LOCALAPPDATA%\Rook\venv\Scripts\python.exe" -c "from rook.learning.command_learner import command_learner; print(len(command_learner.knowledge_store.patterns))"
   ```
   Should print a number (e.g., 89)

2. **Check for JSON syntax errors:**
   - Open `%LOCALAPPDATA%\Rook\data\commands\command_knowledge.json` in a text editor
   - Look for parsing errors

3. **Rebuild knowledge:**
   ```bash
   "%LOCALAPPDATA%\Rook\venv\Scripts\python.exe" -c "from rook.learning.command_learner import command_learner; command_learner.consolidate_knowledge()"
   ```

---

## Diagnostic Commands

### In Rhino

| Command | Purpose |
|---------|---------|
| `PlugInManager` | Check if RookNative and Rook are loaded |
| `ShowRookChat` | Open the Rook chat panel |

The HTTP server auto-starts when RookNative loads — there are no manual start/stop commands.

### In Terminal

```bash
# The HTTP port is OS-assigned. Find it from the discovery file:
dir %LOCALAPPDATA%\Rook\discovery\
type %LOCALAPPDATA%\Rook\discovery\instance-*-native.json

# Then test (replace PORT with the port from the discovery file):
curl http://localhost:PORT/ping
```

### In Claude

```
/mcp                    # List available MCP servers and tools
ping Rhino              # Test connection
rhino_document          # Get document info
```

### Check Configuration Files

**Claude Code config:**
```bash
claude mcp list
```

**Claude Desktop config:**
```
%APPDATA%\Claude\claude_desktop_config.json
```

**Python environment:**
```bash
"%LOCALAPPDATA%\Rook\venv\Scripts\python.exe" --version
"%LOCALAPPDATA%\Rook\venv\Scripts\pip.exe" list
```

---

## Still Having Issues?

1. **Check GitHub Issues:** [github.com/bringfire/rook-release/issues](https://github.com/bringfire/rook-release/issues)

2. **Collect diagnostic info:**
   - Rhino version (`Help > About Rhinoceros`)
   - Windows version
   - Claude client and version
   - Error messages from Rhino command line
   - Contents of configuration files

3. **Open a new issue** with the diagnostic info above

---

## Reinstalling from Scratch

If all else fails, do a clean reinstall:

1. **Uninstall via Add/Remove Programs** (Windows Settings → Apps → Rook)

2. **Remove the Rhino plugin manually** (if it remains):
   ```bash
   rmdir /s /q "%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"
   ```

3. **Remove the Claude Code config entry:**
   ```bash
   claude mcp remove rook --scope user
   ```

4. **Download and re-run the installer** from [GitHub Releases](https://github.com/bringfire/rook-release/releases)

5. **Restart Rhino and Claude clients**
