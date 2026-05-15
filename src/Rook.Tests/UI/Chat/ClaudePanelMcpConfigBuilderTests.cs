using System;
using System.Text.Json;
using Rook.UI.Chat;
using Xunit;

namespace Rook.Tests.UI.Chat
{
    public class ClaudePanelMcpConfigBuilderTests
    {
        [Fact]
        public void BuildStrictRookConfig_CopiesOnlyRookAndAddsPanelLockEnv()
        {
            var sourceJson = """
            {
              "mcpServers": {
                "rook": {
                  "type": "stdio",
                  "command": "C:/Python/python.exe",
                  "args": ["-m", "rook"],
                  "cwd": "C:/Rook/mcp_server",
                  "env": {
                    "PYTHONPATH": "",
                    "PYTHONHOME": "",
                    "ROOK_INSTALL_ROOT": "C:/Rook",
                    "ROOK_DATA_DIR": "C:/Users/aryan/AppData/Roaming/Rook",
                    "ROOK_MODE": "dev",
                    "CHIRP_HOME": "C:/Chirp"
                  }
                },
                "filesystem": {
                  "command": "node"
                }
              }
            }
            """;

            var result = ClaudePanelMcpConfigBuilder.BuildStrictRookConfigJson(
                sourceJson,
                rhinoProcessId: 7101,
                documentSerialNumber: 42);

            using var doc = JsonDocument.Parse(result);
            var servers = doc.RootElement.GetProperty("mcpServers");
            Assert.True(servers.TryGetProperty("rook", out var rook));
            Assert.False(servers.TryGetProperty("filesystem", out _));
            Assert.Equal("C:/Python/python.exe", rook.GetProperty("command").GetString());
            Assert.Equal("C:/Rook/mcp_server", rook.GetProperty("cwd").GetString());
            var env = rook.GetProperty("env");
            Assert.Equal("panel_locked", env.GetProperty("ROOK_MCP_TARGET_MODE").GetString());
            Assert.Equal("7101", env.GetProperty("ROOK_MCP_TARGET_PROCESS_ID").GetString());
            Assert.Equal("42", env.GetProperty("ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER").GetString());
            Assert.Equal("C:/Rook", env.GetProperty("ROOK_INSTALL_ROOT").GetString());
            Assert.Equal("C:/Chirp", env.GetProperty("CHIRP_HOME").GetString());
        }

        [Fact]
        public void BuildStrictRookConfig_MissingRookEntryThrowsActionableError()
        {
            var sourceJson = """{ "mcpServers": { "filesystem": { "command": "node" } } }""";

            var ex = Assert.Throws<InvalidOperationException>(() =>
                ClaudePanelMcpConfigBuilder.BuildStrictRookConfigJson(
                    sourceJson,
                    rhinoProcessId: 7101,
                    documentSerialNumber: 42));

            Assert.Contains("rook", ex.Message, StringComparison.OrdinalIgnoreCase);
            Assert.Contains("MCP", ex.Message, StringComparison.OrdinalIgnoreCase);
        }
    }
}
