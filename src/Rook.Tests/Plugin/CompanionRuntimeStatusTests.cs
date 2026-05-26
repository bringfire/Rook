using System;
using System.Text.Json;
using Rook.Startup;
using Xunit;

namespace Rook.Tests.Plugin
{
    public class CompanionRuntimeStatusTests
    {
        [Theory]
        [InlineData(@"C:\Users\a\AppData\Roaming\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net48\Rook.rhp", "net48")]
        [InlineData(@"C:/Users/a/AppData/Roaming/McNeel/Rhinoceros/8.0/Plug-ins/RookNative/net7.0/Rook.rhp", "net7.0")]
        [InlineData(@"C:\Users\a\AppData\Roaming\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0\Rook.rhp", "net8.0")]
        [InlineData(@"C:\Users\a\AppData\Roaming\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\Rook.rhp", "unknown")]
        public void InferRuntimeChild_UsesRookNativeRuntimePathSegment(
            string assemblyLocation,
            string expected)
        {
            Assert.Equal(
                expected,
                CompanionRuntimeStatus.InferRuntimeChild(assemblyLocation));
        }

        [Fact]
        public void BuildJson_IncludesRuntimeSelfReportFields()
        {
            var onLoadUtc = DateTimeOffset.Parse("2026-05-26T18:00:00Z");
            var startupCompleteUtc = DateTimeOffset.Parse("2026-05-26T18:00:05Z");
            var snapshot = new CompanionRuntimeStatusSnapshot(
                ProcessId: 1234,
                ProcessName: "Revit",
                RhinoInside: true,
                AssemblyLocation: @"C:\Users\a\AppData\Roaming\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net48\Rook.rhp",
                TargetFramework: ".NETFramework,Version=v4.8",
                StartupGateAttached: true,
                DeferredLocalStartupComplete: true,
                StartupComplete: true,
                BridgeRegistered: true,
                OnLoadUtc: onLoadUtc,
                StartupCompleteUtc: startupCompleteUtc);

            using var document = JsonDocument.Parse(
                CompanionRuntimeStatus.BuildJson(snapshot));
            var root = document.RootElement;

            Assert.Equal(1, root.GetProperty("schemaVersion").GetInt32());
            Assert.Equal(1234, root.GetProperty("processId").GetInt32());
            Assert.Equal("Revit", root.GetProperty("processName").GetString());
            Assert.True(root.GetProperty("rhinoInside").GetBoolean());
            Assert.Equal(snapshot.AssemblyLocation, root.GetProperty("assemblyLocation").GetString());
            Assert.Equal("net48", root.GetProperty("runtimeChild").GetString());
            Assert.Equal(".NETFramework,Version=v4.8", root.GetProperty("targetFramework").GetString());
            Assert.True(root.GetProperty("startupGateAttached").GetBoolean());
            Assert.True(root.GetProperty("deferredLocalStartupComplete").GetBoolean());
            Assert.True(root.GetProperty("startupComplete").GetBoolean());
            Assert.True(root.GetProperty("bridgeRegistered").GetBoolean());
            Assert.Equal("2026-05-26T18:00:00.0000000+00:00", root.GetProperty("onLoadUtc").GetString());
            Assert.Equal("2026-05-26T18:00:05.0000000+00:00", root.GetProperty("startupCompleteUtc").GetString());
        }
    }
}
