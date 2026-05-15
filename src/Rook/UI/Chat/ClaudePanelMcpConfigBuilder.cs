using System;
using System.Globalization;
using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Rook.UI.Chat
{
    internal static class ClaudePanelMcpConfigBuilder
    {
        internal const string TargetModeEnv = "ROOK_MCP_TARGET_MODE";
        internal const string TargetProcessIdEnv = "ROOK_MCP_TARGET_PROCESS_ID";
        internal const string TargetDocumentSerialEnv = "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER";

        public static string BuildStrictRookConfigJson(
            string sourceConfigJson,
            int rhinoProcessId,
            uint documentSerialNumber)
        {
            var parsed = JsonNode.Parse(sourceConfigJson);
            if (parsed is null)
                throw new InvalidOperationException("Claude MCP config is not valid JSON.");

            var root = parsed.AsObject();
            var serversNode = root["mcpServers"];
            if (serversNode is null)
                throw new InvalidOperationException("Claude MCP config does not contain mcpServers.");

            var servers = serversNode.AsObject();
            var rookNode = servers["rook"];
            if (rookNode is null)
                throw new InvalidOperationException("Claude MCP config does not contain a rook MCP server entry.");

            var rook = rookNode.DeepClone().AsObject();
            var envNode = rook["env"];
            var env = envNode is null ? new JsonObject() : envNode.AsObject();
            rook["env"] = env;

            env[TargetModeEnv] = "panel_locked";
            env[TargetProcessIdEnv] = rhinoProcessId.ToString(CultureInfo.InvariantCulture);
            env[TargetDocumentSerialEnv] = documentSerialNumber.ToString(CultureInfo.InvariantCulture);

            var output = new JsonObject
            {
                ["mcpServers"] = new JsonObject
                {
                    ["rook"] = rook
                }
            };

            return output.ToJsonString(new JsonSerializerOptions { WriteIndented = true });
        }

        public static string WriteTempConfig(
            string sourceConfigPath,
            int rhinoProcessId,
            uint documentSerialNumber)
        {
            if (!File.Exists(sourceConfigPath))
                throw new FileNotFoundException("Claude MCP config file was not found.", sourceConfigPath);

            var sourceJson = File.ReadAllText(sourceConfigPath);
            var configJson = BuildStrictRookConfigJson(
                sourceJson,
                rhinoProcessId,
                documentSerialNumber);

            var dir = Path.Combine(Path.GetTempPath(), "rook", "claude-code-panel");
            Directory.CreateDirectory(dir);
            var path = Path.Combine(dir, $"rook-panel-{Guid.NewGuid():N}.json");
            File.WriteAllText(path, configJson);
            return path;
        }
    }
}
