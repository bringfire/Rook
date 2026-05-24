# Rook Troubleshooting Guide

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

- Use `rhino_execute_intent` instead of `rhino_command` — it routes through typed endpoints that don't trigger modal dialogs
- Avoid `rhino_execute` and `rhino_command` with `RunScript` — syntax errors cause unrecoverable modal dialogs
- If you must use commands directly, query `knowledge_query(intent="...", depth="context")` first for exact syntax

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
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

4. **Check if uv is already installed:**
   ```bash
   uv --version
   ```

After manual installation, run `install.bat` again.

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
   install.bat
   ```

3. **Check disk space** - The virtual environment needs ~6GB

4. **Check folder permissions** - Ensure you have write access to the installation folder

---

### Dependencies fail to install

**Symptoms:**
- "ERROR: Failed to install dependencies"
- Package resolution errors

**Solutions:**

1. **Retry installation:**
   ```bash
   cd mcp_server
   uv pip install -e . --verbose
   ```

   Source bootstrap installs into `mcp_server/.venv`.
   Release installs use the managed runtime under `%LOCALAPPDATA%\Rook\venv`.

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

   Release install writes Claude Code config to:
   ```
   ~/.claude.json
   ```

   Source bootstrap writes repo-scoped Claude Code config to:
   ```
   .mcp.json
   ```

   For Claude Desktop, check:
   ```
   %APPDATA%\Claude\claude_desktop_config.json
   ```
   Should contain `rook` in `mcpServers`

3. **Re-run installer:**
   ```bash
   install.bat
   ```

4. **Manual configuration for Claude Code:**
   ```bash
   claude mcp add --scope user rook "C:/path/to/mcp_server/.venv/Scripts/python.exe" -- -m rook
   ```

   For release installs, use the managed runtime at:
   ```
   %LOCALAPPDATA%\Rook\venv\Scripts\python.exe
   ```

---

### MCP tools show errors in Claude

**Symptoms:**
- Tools appear but return errors
- "Module not found" errors

**Solutions:**

1. **Verify MCP server can load:**
   ```bash
   cd mcp_server
   .venv\Scripts\python -m rook
   ```
   Press Ctrl+C to exit. Should not show import errors.

2. **Check Python path in config:**
   - Source bootstrap must point to `mcp_server/.venv`
   - Release install must point to `%LOCALAPPDATA%\Rook\venv`
   - Path should use forward slashes: `C:/Users/...`

3. **Reinstall dependencies:**
   ```bash
   cd mcp_server
   uv pip install -e . --force-reinstall
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

2. **Re-run installer to copy plugin:**
   ```bash
   install.bat
   ```

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

## MCP Server Issues

### Server module fails to import

**Symptoms:**
- `import rook` fails
- Missing module errors

**Solutions:**

1. **Verify virtual environment:**
   ```bash
   cd mcp_server
   .venv\Scripts\python -c "import rook; print('OK')"
   ```

   For release installs:
   ```bash
   %LOCALAPPDATA%\Rook\venv\Scripts\python.exe -c "import rook; print('OK')"
   ```

2. **Reinstall in editable mode:**
   ```bash
   cd mcp_server
   uv pip install -e .
   ```

3. **Check `pyproject.toml` exists in `mcp_server/`**

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
- `rhino_execute_intent` doesn't work

**Solutions:**

1. **Verify knowledge directory exists:**
   ```
   knowledge/commands/command_knowledge.json
   ```

   Release installs package `knowledge/` alongside the installed payload and register:
   - `ROOK_INSTALL_ROOT=<install root>`
   - `ROOK_DATA_DIR=%LOCALAPPDATA%\Rook\data`

   Dev bootstrap registers:
   - `ROOK_INSTALL_ROOT=<repo root>`
   - `ROOK_DATA_DIR=<repo root>\knowledge`

2. **Re-download release** - Knowledge might be missing from extraction

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
   cd mcp_server
   .venv\Scripts\python -c "from rook.learning.command_learner import command_learner; print(len(command_learner.knowledge_store.patterns))"
   ```
   Should print a number (e.g., 89)

2. **Check for JSON syntax errors:**
   - Open `knowledge/commands/command_knowledge.json` in a text editor
   - Look for parsing errors

3. **Rebuild knowledge:**
   ```bash
   cd mcp_server
   .venv\Scripts\python -c "from rook.learning.command_learner import command_learner; command_learner.consolidate_knowledge()"
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
cd mcp_server
.venv\Scripts\python --version
.venv\Scripts\pip list
```

---

## Still Having Issues?

1. **Check GitHub Issues:** [github.com/bringfire/Rook/issues](https://github.com/bringfire/Rook/issues)

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

1. **Remove existing installation:**
   ```bash
   # Delete the venv
   rmdir /s /q mcp_server\.venv

   # Remove Claude Code config
   claude mcp remove rook --scope user

   # Backup and remove Claude Desktop config entry manually
   notepad %APPDATA%\Claude\claude_desktop_config.json
   ```

2. **Remove Rhino plugin:**
   ```bash
   rmdir /s /q "%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"
   ```

3. **Re-run installer:**
   ```bash
   install.bat
   ```

4. **Restart Rhino and Claude clients**
