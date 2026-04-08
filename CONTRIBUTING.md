# Contributing to Rook

Thanks for your interest in contributing. Rook is an open-source bridge between AI agents and Rhino 3D / Grasshopper, and contributions of all kinds are welcome.

## Ways to contribute

- Report bugs via GitHub Issues
- Request features via GitHub Issues
- Submit pull requests for fixes, new MCP tools, knowledge entries, or documentation
- Share knowledge by contributing patterns, recipes, or component notes to the knowledge store

For security vulnerabilities, see [SECURITY.md](SECURITY.md). Please do not open public issues for security reports.

## Development setup

See [BUILDING.md](BUILDING.md) for the full development environment setup, including:

- C++ native plugin build (Visual Studio 2022, C++ Desktop workload)
- C# companion plugin build (.NET 8 SDK, .NET Framework 4.8 targeting pack)
- Python MCP server setup (Python 3.12+, uv recommended)
- Rhino 8 with Grasshopper

For a quick install of the latest release, see [QUICK_START.md](QUICK_START.md).

## Pull request process

1. Open an issue first for non-trivial changes. This avoids duplicate work and lets us discuss the approach.
2. Fork the repo and create a topic branch from `main`.
3. Make your changes with clear commit messages.
4. Run the tests before submitting:
   - Python: `pytest -m "not requires_rhino"` from `mcp_server/`
   - Live tests requiring Rhino: see `BUILDING.md`
5. Submit a PR against `main` with a clear description of the change and its motivation.
6. Respond to review feedback. Most PRs will receive review comments — address them or discuss alternatives.

## Code style

- **Python:** PEP 8, type hints encouraged. We use `ruff` for linting where applicable.
- **C++:** Follow the surrounding code style in `src/RookNative/`. Header-only utilities go in `Infrastructure/`.
- **C#:** Standard .NET conventions, follow the patterns in `src/Rook/`.

## Knowledge contributions

Rook learns from observation. The knowledge stores in `knowledge/` accept contributions via:

- Patterns extracted from real Grasshopper definitions
- Component notes describing usage, gotchas, and wiring patterns
- Rhino command observations capturing successful command syntax

Open an issue to ask about contributing knowledge entries.

## Code of conduct

This project follows a [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to abide by its terms.

## License

By contributing, you agree that your contributions will be licensed under the same [MIT License](LICENSE) that covers the project.
