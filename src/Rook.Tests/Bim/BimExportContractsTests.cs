using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim
{
    public class BimExportContractsTests
    {
        private static BimExportOutput ValidOutput() =>
            new BimExportOutput { Directory = @"C:\fixtures", Name = "walls" };

        [Fact]
        public void Validate_RejectsNeitherSelectorNorIdentities()
        {
            var request = new BimExportElementsRequest { Output = ValidOutput() };
            var result = request.Validate();
            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.InvalidScope, result.ErrorCode);
        }

        [Fact]
        public void Validate_RejectsBothSelectorAndIdentities()
        {
            var request = new BimExportElementsRequest
            {
                Output = ValidOutput(),
                Selector = new BimQueryElementsRequest { Category = "Walls" },
                Identities = new System.Collections.Generic.List<BimElementIdentity>
                {
                    new BimElementIdentity { UniqueId = "abc" },
                },
            };
            var result = request.Validate();
            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.InvalidScope, result.ErrorCode);
        }

        [Fact]
        public void Validate_AcceptsSelectorOnly_AndDefaultsRoomsToBoth()
        {
            var request = new BimExportElementsRequest
            {
                Output = ValidOutput(),
                Selector = new BimQueryElementsRequest { Category = "Walls" },
            };
            var result = request.Validate();
            Assert.True(result.Success);
            Assert.Equal(BimRoomsMode.Both, request.EffectiveRooms);
        }

        [Fact]
        public void Validate_RejectsMissingOutputDirectoryOrName()
        {
            var request = new BimExportElementsRequest
            {
                Selector = new BimQueryElementsRequest { Category = "Walls" },
                Output = new BimExportOutput { Name = "walls" },
            };
            var result = request.Validate();
            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.OutputPathInvalid, result.ErrorCode);
        }

        [Fact]
        public void Validate_PropagatesSelectorValidationFailure()
        {
            // document scope with no category is invalid in the underlying selector
            var request = new BimExportElementsRequest
            {
                Output = ValidOutput(),
                Selector = new BimQueryElementsRequest { Scope = BimQueryScope.Document },
            };
            var result = request.Validate();
            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.UnboundedDocumentQuery, result.ErrorCode);
        }
    }
}
