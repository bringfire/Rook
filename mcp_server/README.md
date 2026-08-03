# Rook MCP Server

MCP server that enables compatible MCP clients to interact with Rhino 3D via the Rook HTTP bridge.

> Current architecture: this MCP server talks to the public native `RookNative` plugin. Do not assume a public C# Rhino plugin on `localhost:9876`; the managed companion is now internal.

## Source installation

```bash
cd mcp_server
pip install -e .
```

## Usage

```bash
python -m rook
```

## Configuration

Register the command with your MCP client. For clients that accept an `.mcp.json`
entry, the shape is:

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

Release installs use Rook's bundled CPython runtime and do not require this source
installation step.

## Optional model-provider setup

The core Rhino/Grasshopper tool bridge does not require a model-provider API key.
Optional DSPy learning and agent features use LiteLLM and require credentials for the
provider you select. Without provider credentials, Rook falls back to the supported
non-model lookup path where available.

### Example: Anthropic

1. Go to [Anthropic Console](https://console.anthropic.com/settings/keys)
2. Create a new API key
3. Copy the key (starts with `sk-ant-...`)

Set the provider's environment variable when you choose that provider:

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

Verify optional DSPy setup:

```python
from rook.learning import configure_dspy, is_configured

# This will raise an error if API key is not set
configure_dspy()
print("DSPy configured successfully!")
```

## Features

### Core MCP tools

Tool discovery is lifecycle-admitted and profile-filtered. Do not rely on one global
count: clients may receive the full, readonly, or lean catalog, with progressive
discovery available where configured.
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
MCP Client
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
