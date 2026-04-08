# Rook MCP Server

MCP server that enables Claude to interact with Rhino 3D via the Rook HTTP bridge.

> Current architecture: this MCP server talks to the public native `RookNative` plugin. Do not assume a public C# Rhino plugin on `localhost:9876`; the managed companion is now internal.

## Installation

```bash
cd mcp_server
pip install -e .
```

## Usage

```bash
python -m rook
```

## Configuration

Add to your Claude Code MCP settings (`.mcp.json`):

```json
{
  "mcpServers": {
    "rook": {
      "command": "python",
      "args": ["-m", "rook"]
    }
  }
}
```

## DSPy Learning System Setup

The learning system uses DSPy for intelligent reasoning and hypothesis generation. This requires an Anthropic API key.

### 1. Get an API Key

1. Go to [Anthropic Console](https://console.anthropic.com/settings/keys)
2. Create a new API key
3. Copy the key (starts with `sk-ant-...`)

### 2. Set the Environment Variable

**Option A: Environment variable (recommended)**

```bash
# Linux/macOS
export ANTHROPIC_API_KEY="sk-ant-..."

# Windows (Command Prompt)
set ANTHROPIC_API_KEY=sk-ant-...

# Windows (PowerShell)
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

**Option B: Create a `.env` file**

```bash
# Copy the example file
cp .env.example .env

# Edit .env and add your key
ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Verify Setup

```python
from rook.learning import configure_dspy, is_configured

# This will raise an error if API key is not set
configure_dspy()
print("DSPy configured successfully!")
```

## Features

### Core MCP Tools (113 tools)
- Geometry creation, transformation, measurement
- Boolean operations, lofting, sweeping
- Layer/material management
- Block operations
- SubD and mesh operations

### Knowledge System
- `knowledge_query` - Query patterns before actions
- `knowledge_record` - Record learnings after actions
- MABWiser integration for adaptive learning

### DSPy Learning (requires API key)
- Hypothesis generation and testing
- Failure diagnosis and fix suggestions
- Pattern consolidation
- Workflow detection

## Architecture

```
Claude Code (CLI)
       |
       | MCP Protocol (stdio)
       v
MCP Server (Python)   <-- This package
       |
       | HTTP (discovered native instance)
       v
RookNative (public Rhino plugin)
       |
       v
Rhino 3D / Grasshopper
```
