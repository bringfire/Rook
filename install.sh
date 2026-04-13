#!/bin/bash

# ============================================================================
# Rook Installer for macOS/Linux
# ============================================================================
# This script:
#   1. Sets up a Python environment with uv
#   2. Installs the Rhino plugin (if on macOS with Rhino)
#   3. Generates MCP configuration files
#   4. Verifies the installation
#
# Note: The Rhino plugin is Windows-only. On macOS/Linux, this installer
# sets up the MCP server so Claude Code / Claude Desktop can connect to
# a Rhino instance running on a Windows machine.
# ============================================================================

set -e

USER_CONFIG=false
if [ "${1:-}" = "--user-config" ]; then
    USER_CONFIG=true
fi

echo ""
echo "============================================================================"
echo "                          Rook Installer"
echo "============================================================================"
echo ""

# Get the directory where this script is located
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOK_MODE="dev"
ROOK_INSTALL_ROOT="$INSTALL_DIR"
ROOK_DATA_DIR="$INSTALL_DIR/knowledge"

# ============================================================================
# Step 1: Setup Python Environment with uv
# ============================================================================
echo "[1/4] Setting up Python environment..."

if ! command -v uv &> /dev/null; then
    echo "   uv not found. Installing uv package manager..."
    echo ""
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    echo "   [OK] uv installed"
else
    echo "   [OK] uv is available"
fi

cd "$INSTALL_DIR/mcp_server"

echo "   Creating virtual environment..."
if ! uv venv .venv --python 3.12 2>/dev/null; then
    echo "   Python 3.12 not found, trying default..."
    if ! uv venv .venv 2>/dev/null; then
        echo "   ERROR: Failed to create virtual environment."
        echo "   Make sure you have network access (uv downloads Python automatically)."
        exit 1
    fi
fi

echo "   Installing dependencies..."
if ! uv pip install -q -e . --python .venv/bin/python; then
    echo "   Retrying with verbose output..."
    uv pip install -e . --python .venv/bin/python
fi

PYTHON_PATH="$INSTALL_DIR/mcp_server/.venv/bin/python"
echo "   [OK] Python environment ready"

cd "$INSTALL_DIR"

# ============================================================================
# Step 2: Install Rhino Plugin
# ============================================================================
echo ""
echo "[2/4] Checking Rhino plugin..."

PLUGIN_INSTALLED=false

if [[ "$OSTYPE" == "darwin"* ]]; then
    RHINO_PLUGINS="$HOME/Library/Application Support/McNeel/Rhinoceros/8.0/Plug-ins"

    if [ -d "$RHINO_PLUGINS" ]; then
        PLUGIN_SRC=""
        if [ -f "$INSTALL_DIR/plugin/Rook.rhp" ]; then
            PLUGIN_SRC="$INSTALL_DIR/plugin"
        elif [ -f "$INSTALL_DIR/src/Rook/bin/Release/net48/Rook.rhp" ]; then
            PLUGIN_SRC="$INSTALL_DIR/src/Rook/bin/Release/net48"
        elif [ -f "$INSTALL_DIR/src/Rook/bin/Release/net7.0/Rook.rhp" ]; then
            PLUGIN_SRC="$INSTALL_DIR/src/Rook/bin/Release/net7.0"
        fi

        if [ -n "$PLUGIN_SRC" ]; then
            PLUGIN_DEST="$RHINO_PLUGINS/Rook"
            mkdir -p "$PLUGIN_DEST"
            cp "$PLUGIN_SRC"/*.rhp "$PLUGIN_DEST/" 2>/dev/null || true
            cp "$PLUGIN_SRC"/*.dll "$PLUGIN_DEST/" 2>/dev/null || true
            cp "$PLUGIN_SRC"/*.rui "$PLUGIN_DEST/" 2>/dev/null || true
            echo "   [OK] Plugin installed to $PLUGIN_DEST"
            PLUGIN_INSTALLED=true
        else
            echo "   [SKIP] Plugin files not found"
        fi
    else
        echo "   [SKIP] Rhino 8 not detected on this Mac"
    fi
else
    echo "   [SKIP] Rhino plugin is Windows/macOS only"
fi

if [ "$PLUGIN_INSTALLED" = false ]; then
    echo "   The MCP server will still work with Claude Code / Claude Desktop"
fi

# ============================================================================
# Step 3: Generate Configuration
# ============================================================================
echo ""
echo "[3/4] Generating configuration..."

# --- Project-level .mcp.json (for Claude Code) ---
# PYTHONPATH/PYTHONHOME are cleared to prevent Rhino's Python from interfering.

cat > "$INSTALL_DIR/.mcp.json" << EOF
{
  "mcpServers": {
    "rook": {
      "type": "stdio",
      "command": "$PYTHON_PATH",
      "args": ["-m", "rook"],
      "cwd": "$INSTALL_DIR/mcp_server",
      "env": {
        "PYTHONPATH": "",
        "PYTHONHOME": "",
        "ROOK_INSTALL_ROOT": "$ROOK_INSTALL_ROOT",
        "ROOK_DATA_DIR": "$ROOK_DATA_DIR",
        "ROOK_MODE": "$ROOK_MODE"
      }
    }
  }
}
EOF

echo "   [OK] .mcp.json generated (repo-level Claude Code config)"

if [ "$USER_CONFIG" = true ]; then
    echo "   Updating user-level Claude Code configuration..."
    "$PYTHON_PATH" << PYEOF
import json
from pathlib import Path

config_path = Path.home() / ".claude.json"
python_path = "$PYTHON_PATH"
cwd_path = "$INSTALL_DIR/mcp_server"

if config_path.exists():
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        config = {}
else:
    config = {}

config.setdefault("mcpServers", {})
config["mcpServers"]["rook"] = {
    "type": "stdio",
    "command": python_path,
    "args": ["-m", "rook"],
    "cwd": cwd_path,
    "env": {
        "PYTHONPATH": "",
        "PYTHONHOME": "",
        "ROOK_INSTALL_ROOT": "$ROOK_INSTALL_ROOT",
        "ROOK_DATA_DIR": "$ROOK_DATA_DIR",
        "ROOK_MODE": "$ROOK_MODE",
    },
}

config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
print("   [OK] ~/.claude.json updated")
PYEOF
fi

# --- Claude Desktop config ---
DESKTOP_CONFIG_DIR=""
if [[ "$OSTYPE" == "darwin"* ]]; then
    DESKTOP_CONFIG_DIR="$HOME/Library/Application Support/Claude"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    DESKTOP_CONFIG_DIR="$HOME/.config/Claude"
fi

if [ "$USER_CONFIG" = true ] && [ -n "$DESKTOP_CONFIG_DIR" ] && [ -d "$DESKTOP_CONFIG_DIR" ]; then
    echo "   Updating Claude Desktop configuration..."
    DESKTOP_CONFIG="$DESKTOP_CONFIG_DIR/claude_desktop_config.json"

    "$PYTHON_PATH" << PYEOF
import json, shutil
from pathlib import Path

config_path = Path("$DESKTOP_CONFIG")
python_path = "$PYTHON_PATH"
cwd_path = "$INSTALL_DIR/mcp_server"

try:
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        shutil.copy2(config_path, config_path.with_suffix('.json.bak'))
    else:
        config = {}

    config.setdefault('mcpServers', {})
    config['mcpServers']['rook'] = {
        'type': 'stdio',
        'command': python_path,
        'args': ['-m', 'rook'],
        'cwd': cwd_path,
        'env': {
            'PYTHONPATH': '',
            'PYTHONHOME': '',
            'ROOK_INSTALL_ROOT': "$ROOK_INSTALL_ROOT",
            'ROOK_DATA_DIR': "$ROOK_DATA_DIR",
            'ROOK_MODE': "$ROOK_MODE",
        }
    }

    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)

    print('   [OK] Claude Desktop configured')
except Exception as e:
    print(f'   WARNING: Claude Desktop config failed: {e}')
PYEOF
else
    if [ "$USER_CONFIG" = true ]; then
        echo "   [SKIP] Claude Desktop not found"
    else
        echo "   [SKIP] User-level Claude Desktop config not requested"
    fi
fi

# --- OpenAI Codex CLI config ---
CODEX_CONFIG_DIR="$HOME/.codex"

echo "   Generating repo-level Codex configuration..."

"$PYTHON_PATH" << PYEOF
from pathlib import Path
import re

python_path = "$PYTHON_PATH"
cwd_path = "$INSTALL_DIR/mcp_server"

toml_content = f"""# Rook MCP Server configuration for OpenAI Codex CLI
# Auto-generated by Rook installer

[mcp_servers.rook]
command = "{python_path}"
args = ["-m", "rook"]
cwd = "{cwd_path}"
startup_timeout_sec = 30
tool_timeout_sec = 120

[mcp_servers.rook.env]
PYTHONPATH = ""
PYTHONHOME = ""
ROOK_INSTALL_ROOT = "$ROOK_INSTALL_ROOT"
ROOK_DATA_DIR = "$ROOK_DATA_DIR"
ROOK_MODE = "$ROOK_MODE"
"""

# Repo-level .codex/config.toml
project_config = Path("$INSTALL_DIR/.codex/config.toml")
project_config.parent.mkdir(exist_ok=True)
project_config.write_text(toml_content, encoding="utf-8")
print(f"   [OK] .codex/config.toml generated (repo-level)")

PYEOF

if [ "$USER_CONFIG" = true ]; then
    echo "   Updating user-level Codex configuration..."
    "$PYTHON_PATH" << PYEOF
from pathlib import Path
import re

toml_content = Path("$INSTALL_DIR/.codex/config.toml").read_text(encoding="utf-8")
user_config = Path.home() / ".codex" / "config.toml"
user_config.parent.mkdir(exist_ok=True)
if user_config.exists():
    existing = user_config.read_text(encoding="utf-8")
    if "[mcp_servers.rook]" in existing:
        merged = re.sub(
            r"\[mcp_servers\.rook\].*?(?=\n\[(?!mcp_servers\.rook[.\]])|$)",
            toml_content.strip(), existing, flags=re.DOTALL)
    else:
        merged = existing.rstrip() + "\n\n" + toml_content
    user_config.write_text(merged, encoding="utf-8")
else:
    user_config.write_text(toml_content, encoding="utf-8")
print("   [OK] ~/.codex/config.toml updated")
PYEOF
fi

CLAUDE_SKILLS_SOURCE="$INSTALL_DIR/.claude/skills"
CLAUDE_AGENTS_SOURCE="$INSTALL_DIR/.claude/agents"
CODEX_SKILLS_SOURCE="$INSTALL_DIR/.agents/skills"
if [ "$USER_CONFIG" = true ] && { [ -d "$CLAUDE_SKILLS_SOURCE" ] || [ -d "$CLAUDE_AGENTS_SOURCE" ] || [ -d "$CODEX_SKILLS_SOURCE" ]; }; then
    [ -d "$CLAUDE_SKILLS_SOURCE" ] && mkdir -p "$HOME/.claude/skills" && cp -R "$CLAUDE_SKILLS_SOURCE"/. "$HOME/.claude/skills/"
    [ -d "$CLAUDE_AGENTS_SOURCE" ] && mkdir -p "$HOME/.claude/agents" && cp -R "$CLAUDE_AGENTS_SOURCE"/. "$HOME/.claude/agents/"
    [ -d "$CODEX_SKILLS_SOURCE" ] && mkdir -p "$HOME/.codex/skills" && cp -R "$CODEX_SKILLS_SOURCE"/. "$HOME/.codex/skills/"
    echo "   [OK] User-level Claude/Codex skills and Claude agents installed"
fi

# ============================================================================
# Step 4: Verify
# ============================================================================
echo ""
echo "[4/4] Verifying installation..."

if $PYTHON_PATH -c "import rook; print('   [OK] MCP server module loads')" 2>/dev/null; then
    true
else
    echo "   WARNING: MCP server module failed to load"
fi

if [ -f "$INSTALL_DIR/knowledge/commands/command_knowledge.json" ]; then
    echo "   [OK] Knowledge store found"
else
    echo "   WARNING: Knowledge store not found"
fi

if [ -f "$INSTALL_DIR/.mcp.json" ]; then
    echo "   [OK] .mcp.json generated"
fi

if [ -f "$INSTALL_DIR/.codex/config.toml" ]; then
    if grep -q "\[mcp_servers\.rook\]" "$INSTALL_DIR/.codex/config.toml" 2>/dev/null; then
        echo "   [OK] Repo-level Codex config generated"
    fi
fi

if [ "$USER_CONFIG" = true ] && [ -f "$HOME/.codex/config.toml" ]; then
    if grep -q "\[mcp_servers\.rook\]" "$HOME/.codex/config.toml" 2>/dev/null; then
        echo "   [OK] Codex CLI has rook configured"
    fi
fi

# ============================================================================
# Done
# ============================================================================
echo ""
echo "============================================================================"
echo "                      Installation Complete!"
echo "============================================================================"
echo ""
echo " NEXT STEPS:"
echo ""
echo " 1. Make sure Rhino 8 is running on Windows with the plugin loaded"
echo ""
echo " 2. Open a terminal in this directory and run:"
echo "       claude"
echo ""
echo " 3. In Claude Code, type /mcp and look for \"rook\""
echo ""
echo " 4. Try: \"ping Rhino\" -- should return \"pong\""
echo ""
echo " Repo-local Claude Code and Codex config is ready in this checkout."
if [ "$USER_CONFIG" = true ]; then
    echo " User-level Claude Code and Codex config was also updated."
fi
echo ""
echo "============================================================================"
echo ""
echo " Install directory: $INSTALL_DIR"
echo ""
