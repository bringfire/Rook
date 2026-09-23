# Security Policy

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

If you discover a security vulnerability in Rook, report it through GitHub's private vulnerability reporting:

1. Go to the [Security tab](../../security) of this repository
2. Click **Report a vulnerability**
3. Fill in the details

You can expect an initial response within 7 days. Once a fix is available, we'll coordinate disclosure with you.

## What to include

- A description of the vulnerability and its impact
- Steps to reproduce, ideally with a minimal repro case
- Affected versions if known
- Any suggested mitigations

## Scope

In scope:
- The C++ native plugin (`src/RookNative/`) and its HTTP server
- The C# companion plugin (`src/Rook/`)
- The Python MCP server (`mcp_server/`) and its agents
- The chat server and any HTTP endpoints exposed by Rook

Out of scope:
- Vulnerabilities in upstream dependencies (Rhino SDK, Grasshopper SDK, third-party Python packages) — please report those to their maintainers directly
- Issues that require local administrator access on the user's machine
- Theoretical attacks without a demonstrated impact path

## Local HTTP surfaces (what Rook exposes on your machine)

Rook runs two local HTTP servers. Neither is reachable from the network.

- **Native server** (`src/RookNative`, inside Rhino). Binds `127.0.0.1` on an
  OS-assigned port published through a discovery file under
  `%LOCALAPPDATA%\Rook\discovery`. Several routes execute code in Rhino by
  design (`/execute`, `/command`, Grasshopper edits) and others write files.
  Any process running as the same user can call it; that is how the MCP
  server, the chat service and the companion plug-in reach Rhino. What it
  refuses is anything a web page can make your browser send. Before routing,
  every request must carry the `X-Rook-Client` header: a page can only add a
  custom header through a CORS-preflighted request and the server never
  answers a preflight, while `<img>`/`<script>` loads, form posts and
  navigations cannot set headers at all. As a second layer it rejects any
  request carrying `Origin` or the browser-set `Sec-Fetch-*` headers. Refusals
  are HTTP 403 (`client_header_required` / `browser_request_rejected`). It
  sends no CORS headers. Rook's own clients send the header; if you script the
  server yourself, add `X-Rook-Client: <anything>` to each request.
- **Chat service** (`mcp_server/src/rook/agent/chat`, a separate Python
  process spawned by the companion). Binds `127.0.0.1` on an OS-assigned port
  and requires a per-launch session nonce (`X-Rook-Session`) on every request
  except `/agent/chat/health`; the RookChat WebView pages send it.

The threat model is therefore: anything already running as your user can do
what Rook can do in Rhino; a web page cannot, because no request a browser
issues without a CORS grant carries the client header, and the native server
grants none. If you find a request a browser can make that gets past either
server, please report it privately.

## Supported versions

Only the latest released version of Rook receives security fixes. Users on older versions should upgrade.

## Disclosure policy

We follow coordinated disclosure. Once a fix ships, we publish a security advisory describing the issue and credit the reporter (unless they prefer to remain anonymous).
