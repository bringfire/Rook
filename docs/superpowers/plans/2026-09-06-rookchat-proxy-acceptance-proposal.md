# Proposed Slice B Transport Acceptance Amendment

Status: **proposal for independent review, not implemented or execution authority**.
Base: `a3cf18f1873172536896b9687e64ef54e3075861`.
V4 remains failed and preserved. Nothing here classifies its 24 bytes as TLS
closure traffic, waives its result, or establishes the cause of its abort.

## Exact Proposed Rule

Replace the blanket "zero proxy refusals or connection failures" condition in
the specification's Slice B paragraph and Task 12's corresponding plan paragraph
with the following bounded rule, only after approval:

> Cold bootstrap requires at least one observed allowlisted host/port admission.
> Destination refusals and allowlist violations are hard failures. Connection
> establishment failures remain hard failures in this amendment. Proxy internal
> forwarding faults, resource-bound failures, missing or malformed evidence,
> and unobserved cleanup remain hard failures. A socket-raised endpoint
> connection abort during forwarding is retained as a transport diagnostic,
> not an independent success or failure verdict for the application. Slice B
> passes only if every existing cold-kernel, runtime/source-identity, provider,
> MCP, filesystem, persistence, cancellation and cleanup assertion passes.
> An empty/start-stop-only proxy ledger still fails. No connection closure,
> error code, pending-byte count or EOF state substitutes for application checks.

This is deliberately narrower than ignoring all network failures. It changes
only forwarding abort treatment; `proxy_connect_failed` is not relaxed.

## Minimal Prospective Implementation

Keep the current proxy, selector loop, buffers, deadlines, journals and cleanup.
Use Python's standard exception classification at the actual socket operation:

- A `ConnectionError` raised directly by `send`, `recv`, or `shutdown(SHUT_WR)`
  may produce `proxy_transport_aborted`, with the existing bounded diagnostics
  plus its exception class. This covers Python's connection-aborted/reset and
  broken-pipe subclasses without matching Windows error constants or text.
- All other exceptions keep their existing fatal path. In particular, selector
  errors, invalid descriptor/argument errors, no-progress writes, stopping with
  pending data, journal limits and cleanup uncertainty cannot be relabeled as
  an endpoint abort. Qualification-initiated stopping is not an abort exemption.
- The proxy terminates the affected tunnel and retains exact owned cleanup;
  it does not replay a write, reconnect, resume, or retry any operation.
- `verify_proxy_observations()` would admit that one new diagnostic event only
  with a valid admitted destination, complete bounded operation/direction/error/
  buffer/EOF/stop metadata, and no stop request. Existing refusal, connect-failure
  and internal-forwarding-failure events remain vetoes. Incomplete classification
  stays fatal; legacy `proxy_forward_failed` records are never retro-converted.
- A non-vetoing transport observation only permits the remaining checks to run.
  It cannot set the run outcome to passed. Missing, failed or unexecuted kernel,
  source, provider, MCP, file, session, cancellation or cleanup checks refuse.
  Retain the full bounded abort ledger in successful evidence too, and report
  the abort count explicitly rather than describing transport as error-free.

No new protocol schema, proxy framework, process monitor, retry mechanism, TLS
interception or product policy is proposed. These are qualification-only rules.
The existing local forwarding correctness and bounded-shutdown tests remain
required. A prospective implementation also needs causal tests proving the new
event cannot turn an incomplete application result or internal proxy fault green.
This proposal does not authorize that implementation or another full execution.

## Local Application Control

Added one three-case parameterized test using the existing real CONNECT proxy,
loopback TCP sockets, and Python's standard `http.client.HTTPResponse` parser.
It is plaintext local test traffic, not interception of public TLS. The upstream
connection is redirected to a local listener through the existing test boundary;
external DNS/network and unexpected subprocesses remain denied.

The local HTTP response declares one exact Content-Length and successful JSON
echo result. In the complete cases the client validates all bytes and the JSON
before allowing server termination. In the interrupted case only half the body
is sent, then the server resets; the standard parser must raise `IncompleteRead`.

| Control | Application result | Real proxy observation | Current acceptance |
| --- | --- | --- | --- |
| Complete body, orderly close | Exact body and success JSON pass | No forwarding failure | Pass |
| Complete body, then TCP reset | Exact body and success JSON pass | Upstream recv reset recorded | Refuse |
| Half body, then TCP reset | `IncompleteRead`; application fails | Upstream recv reset recorded | Refuse |

Both reset cases produced the same diagnostic properties locally: `recv` on
`upstream`, direction `upstream_to_client`, errno/winerror 10054, zero pending
bytes, no observed EOF, neither write side closed, no stop request. Their
application outcomes differ. Thus even zero pending bytes plus identical error
metadata cannot establish application success. All exact test threads stopped;
proxy shutdown remained bounded. No acceptance code was changed to get a pass.

This control does not explain V4's different client-send/10053/24-byte record,
prove public TLS response completeness, or qualify the real bootstrap. Those
claims remain outside its scope. Real bootstrap requires its existing independent
kernel/application evidence, not inference from this local control.

## Evidence

Working directory: `C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server`.

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
& ./.venv/Scripts/python.exe -I -B -m pytest -p pytest_asyncio.plugin tests/test_rookchat_prime_acp_qualification.py -k 'proxy_application_result_is_independent' -q --tb=short --junitxml=../artifacts/task12-slice-a-preflight/v4-proxy-policy-control.xml -o junit_logging=all -o junit_log_passing_tests=true
```

Result: **3 passed, 197 deselected**, exit 0, 1.84 seconds.
JUnit SHA-256: `6DD3954E3552854BB3B79BFFCBED94B263365437D85FAD3E31DB5DD1A36A0808`.
It retains the three application outcomes and actual proxy failure snapshots.
No Prime, kernel, provider-model, Rhino or Grasshopper process was launched.

The complete same-file regression command (same environment and directory):

```powershell
& ./.venv/Scripts/python.exe -I -B -m pytest -p pytest_asyncio.plugin tests/test_rookchat_prime_acp_qualification.py -q --tb=short --junitxml=../artifacts/task12-slice-a-preflight/v4-proxy-policy-regression.xml
```

Result: **200 passed**, exit 0, 47.52 seconds.
JUnit SHA-256: `30C11A9F9DA2B580175B5687C387AF8061166372CC6BA9D035C59FCF65CE6580`.
The precontact runner, deterministic provider/proxy, product code, protocols,
frozen specification and implementation plan remain unchanged. Only this
non-governing proposal and the local control test are added for review.
