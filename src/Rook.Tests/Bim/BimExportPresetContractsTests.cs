using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim
{
    public class BimExportPresetContractsTests
    {
        private static BimExportOutput ValidOutput() =>
            new BimExportOutput { Directory = @"C:\fixtures", Name = "shell" };

        [Fact]
        public void Validate_RejectsMissingPreset()
        {
            var request = new BimExportPresetRequest { Output = ValidOutput() };
            var result = request.Validate();
            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.UnknownPreset, result.ErrorCode);
        }

        [Fact]
        public void Validate_RejectsMissingOutput()
        {
            var request = new BimExportPresetRequest
            {
                Preset = "architectural_shell",
                Output = new BimExportOutput { Name = "shell" },
            };
            var result = request.Validate();
            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.OutputPathInvalid, result.ErrorCode);
        }

        [Fact]
        public void Validate_RejectsInvalidScope()
        {
            var request = new BimExportPresetRequest
            {
                Preset = "architectural_shell",
                Output = ValidOutput(),
                Scope = "sideways",
            };
            var result = request.Validate();
            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.InvalidScope, result.ErrorCode);
        }

        [Fact]
        public void EffectiveScope_DefaultsToActiveView()
        {
            var request = new BimExportPresetRequest { Preset = "x", Output = ValidOutput() };
            Assert.Equal(BimQueryScope.ActiveView, request.EffectiveScope);
        }

        [Fact]
        public void EffectiveScope_ParsesDocument()
        {
            var request = new BimExportPresetRequest { Preset = "x", Output = ValidOutput(), Scope = "document" };
            Assert.Equal(BimQueryScope.Document, request.EffectiveScope);
        }
    }
}
