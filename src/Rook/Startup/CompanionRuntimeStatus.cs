using System;
using System.Diagnostics;
using System.IO;
using System.Collections.Generic;
using System.Reflection;
using System.Runtime.Versioning;
using System.Text.Json;
using Rook.Capabilities;

namespace Rook.Startup
{
    internal sealed record CompanionRuntimeStatusSnapshot(
        int ProcessId,
        string ProcessName,
        bool RhinoInside,
        string AssemblyLocation,
        string TargetFramework,
        bool StartupGateAttached,
        bool DeferredLocalStartupComplete,
        bool StartupComplete,
        bool BridgeRegistered,
        bool PanelsRegistered,
        IReadOnlyList<CapabilityDomainStatus> CapabilityDomains,
        DateTimeOffset OnLoadUtc,
        DateTimeOffset? StartupCompleteUtc);

    internal static class CompanionRuntimeStatus
    {
        public static string InferRuntimeChild(string assemblyLocation)
        {
            if (string.IsNullOrWhiteSpace(assemblyLocation))
            {
                return "unknown";
            }

            var segments = assemblyLocation.Split(
                new[] { '\\', '/' },
                StringSplitOptions.RemoveEmptyEntries);
            foreach (var segment in segments)
            {
                if (string.Equals(segment, "net48", StringComparison.OrdinalIgnoreCase))
                {
                    return "net48";
                }

                if (string.Equals(segment, "net7.0", StringComparison.OrdinalIgnoreCase))
                {
                    return "net7.0";
                }

                if (string.Equals(segment, "net8.0", StringComparison.OrdinalIgnoreCase))
                {
                    return "net8.0";
                }
            }

            return "unknown";
        }

        public static string GetStatusFilePath(int processId)
        {
            return Path.Combine(
                RookPaths.SharedDiscoveryFolder,
                $"companion-{processId}.json");
        }

        public static string ReadTargetFramework(Assembly assembly)
        {
            return assembly
                .GetCustomAttribute<TargetFrameworkAttribute>()
                ?.FrameworkName
                ?? string.Empty;
        }

        public static CompanionRuntimeStatusSnapshot CreateSnapshot(
            bool rhinoInside,
            bool startupGateAttached,
            bool deferredLocalStartupComplete,
            bool startupComplete,
            bool bridgeRegistered,
            bool panelsRegistered,
            DateTimeOffset onLoadUtc,
            DateTimeOffset? startupCompleteUtc)
        {
            var process = Process.GetCurrentProcess();
            var assembly = typeof(RookPlugin).Assembly;
            return new CompanionRuntimeStatusSnapshot(
                ProcessId: process.Id,
                ProcessName: process.ProcessName,
                RhinoInside: rhinoInside,
                AssemblyLocation: assembly.Location,
                TargetFramework: ReadTargetFramework(assembly),
                StartupGateAttached: startupGateAttached,
                DeferredLocalStartupComplete: deferredLocalStartupComplete,
                StartupComplete: startupComplete,
                BridgeRegistered: bridgeRegistered,
                PanelsRegistered: panelsRegistered,
                CapabilityDomains: CapabilityDomainStatusBuilder.BuildCompanionDomains(
                    rhinoInside,
                    startupComplete,
                    bridgeRegistered,
                    panelsRegistered),
                OnLoadUtc: onLoadUtc,
                StartupCompleteUtc: startupCompleteUtc);
        }

        public static string BuildJson(CompanionRuntimeStatusSnapshot snapshot)
        {
            var payload = new
            {
                schemaVersion = 1,
                processId = snapshot.ProcessId,
                processName = snapshot.ProcessName,
                rhinoInside = snapshot.RhinoInside,
                assemblyLocation = snapshot.AssemblyLocation,
                runtimeChild = InferRuntimeChild(snapshot.AssemblyLocation),
                targetFramework = snapshot.TargetFramework,
                startupGateAttached = snapshot.StartupGateAttached,
                deferredLocalStartupComplete = snapshot.DeferredLocalStartupComplete,
                startupComplete = snapshot.StartupComplete,
                bridgeRegistered = snapshot.BridgeRegistered,
                panelsRegistered = snapshot.PanelsRegistered,
                capabilityDomains = snapshot.CapabilityDomains,
                onLoadUtc = snapshot.OnLoadUtc.ToUniversalTime().ToString("O"),
                startupCompleteUtc = snapshot.StartupCompleteUtc?.ToUniversalTime().ToString("O"),
                statusUpdatedUtc = DateTimeOffset.UtcNow.ToString("O"),
            };

            return JsonSerializer.Serialize(
                payload,
                new JsonSerializerOptions
                {
                    WriteIndented = true,
                    PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
                });
        }

        public static void Write(CompanionRuntimeStatusSnapshot snapshot)
        {
            var path = GetStatusFilePath(snapshot.ProcessId);
            var directory = Path.GetDirectoryName(path);
            if (!string.IsNullOrWhiteSpace(directory))
            {
                Directory.CreateDirectory(directory);
            }

            var tempPath = path + ".tmp";
            File.WriteAllText(tempPath, BuildJson(snapshot));
            if (File.Exists(path))
            {
                File.Replace(tempPath, path, null);
            }
            else
            {
                File.Move(tempPath, path);
            }
        }
    }
}
