# Contributing to Rook

Rook is open source under the [MIT License](LICENSE). Bug reports, questions,
ideas and pull requests are all welcome.

## Reporting issues

- **Bug** — open a [GitHub issue](https://github.com/bringfire/Rook/issues)
  describing what you did, what you expected, and what actually happened.
- **Feature request** — open an issue describing the outcome you want.
- **Question** — open an issue, or email **bringfiregames@gmail.com**.
- **Security vulnerability** — see [SECURITY.md](SECURITY.md). Please do
  **not** open a public issue for security reports.

A good bug report includes your OS and **Rhino version**, the AI client you use
(Claude Code, Codex, Cursor, …), what you asked Rook to do, what happened, and
any error text from the Rhino command line or the MCP client.

## Building from source

See [BUILDING.md](BUILDING.md). It covers every component a full build needs:
the C++ native plug-in, the C# companion, the Python MCP server, the Chirp
sibling repository, the FFmpeg payload, the Prime runtime download, and the
installer.

## Pull requests

1. Open an issue first for anything larger than a small fix, so the approach can
   be agreed before you invest time.
2. Branch from `main`. Keep one change per pull request.
3. Add or update tests with the change:
   - Python: `mcp_server/tests` (`pytest`); `test_server_tool_profiles.py` is the
     authoritative count contract for the MCP tool surface, so a new tool must
     be classified in `targeting.py` and `mcp_tool_profiles.py` and the counts
     updated in both pinned tests.
   - C#: `src/Rook.Tests` (`dotnet test`).
   - Native: the validation tests under `src/RookNative`.
4. Run the relevant suites locally before opening the PR and say in the
   description what you ran.
5. Describe *why* as well as *what*. If the change touches a live Rhino or
   Grasshopper path, note how you verified it against a running Rhino.

Pull requests are squash-merged. Maintainers review for correctness, Rhino
thread-safety (all HTTP handling serializes through the Rhino UI thread), and
fit with the typed-route design described in `docs/CURRENT_ARCHITECTURE.md`.

## Code of conduct

Be respectful and constructive. Reports of unacceptable behaviour can be sent to
**bringfiregames@gmail.com**.

## License of contributions

By submitting a pull request you agree that your contribution is licensed under
the MIT License, the same as the rest of Rook.
