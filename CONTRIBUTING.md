# Contributing to Rook

Rook is open source under the [MIT License](LICENSE). Bug reports, questions
and ideas are welcome. Code changes are welcome **by invitation**: a pull request
is accepted only for an issue a maintainer has marked `accepted` or `help wanted`.
Unsolicited pull requests are closed with a pointer to this page. Nothing personal:
Rook is maintained by one person, every change has to pass a live Rhino and
Rhino.Inside.Revit gate, and the queue has to stay short enough to review well.

MIT means you never need permission to fork, modify or redistribute Rook. A fork
is the right home for work that has not been accepted here.

## Reporting issues

- **Bug** — open a [GitHub issue](https://github.com/bringfire/Rook/issues)
  describing what you did, what you expected, and what actually happened.
- **Feature request** — open an issue describing the outcome you want.
- **Question** — use [Discussions](https://github.com/bringfire/Rook/discussions),
  or email **bringfiregames@gmail.com**.
- **Security vulnerability** — see [SECURITY.md](SECURITY.md). Please do
  **not** open a public issue for security reports.

A good bug report includes your OS and **Rhino version**, the AI client you use
(Claude Code, Codex, Cursor, …), what you asked Rook to do, what happened, and
any error text from the Rhino command line or the MCP client.

## How a change gets in

1. Open an issue first. Say what you want to change and why.
2. Wait for a maintainer to mark it `accepted` (we will do it) or `help wanted`
   (a pull request from you is welcome). Issues without either label are not
   open for pull requests.
3. Branch from `main`. Keep one change per pull request, and link the issue in
   the pull request description.
4. Add or update tests with the change:
   - Python: `mcp_server/tests` (`pytest`); `test_server_tool_profiles.py` is the
     authoritative count contract for the MCP tool surface, so a new tool must
     be classified in `targeting.py` and `mcp_tool_profiles.py` and the counts
     updated in both pinned tests.
   - C#: `src/Rook.Tests` (`dotnet test`).
   - Native: the validation tests under `src/RookNative`.
5. Run the relevant suites locally before opening the PR and say in the
   description what you ran. If the change touches a live Rhino or Grasshopper
   path, note how you verified it against a running Rhino.
6. Describe *why* as well as *what*.

Pull requests are squash-merged. Maintainers review for correctness, Rhino
thread-safety (all HTTP handling serializes through the Rhino UI thread), and
fit with the typed-route design described in `docs/CURRENT_ARCHITECTURE.md`.
Review happens when time allows; there is no response-time commitment.

## Building from source

See [BUILDING.md](BUILDING.md). It covers every component a full build needs:
the C++ native plug-in, the C# companion, the Python MCP server, the Chirp
sibling repository, the FFmpeg payload, the Prime runtime download, and the
installer.

## Code of conduct

Be respectful and constructive. Reports of unacceptable behaviour can be sent to
**bringfiregames@gmail.com**.

## License of contributions

By submitting a pull request you agree that your contribution is licensed under
the MIT License, the same as the rest of Rook.
