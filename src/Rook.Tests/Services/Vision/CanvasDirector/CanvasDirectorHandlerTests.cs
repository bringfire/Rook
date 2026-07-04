using System;
using System.Text.Json;
using Rook.Services.Vision.CanvasDirector;
using Xunit;

namespace Rook.Tests.Services.Vision.CanvasDirector
{
    public class CanvasDirectorHandlerTests
    {
        [Fact]
        public void Dispatch_MissingOp_ReturnsInvalidInput400()
        {
            var response = new CanvasDirectorHandler(new FakeExtractor()).Dispatch("{}");

            Assert.False(response.Success);
            Assert.Equal(400, response.HttpStatus);
            AssertError(response.Data, "invalid_input", "missing required 'op'");
        }

        [Fact]
        public void Dispatch_UnknownOp_ReturnsInvalidInput400AndMentionsOp()
        {
            var response = new CanvasDirectorHandler(new FakeExtractor()).Dispatch("{\"op\":\"dance\"}");

            Assert.False(response.Success);
            Assert.Equal(400, response.HttpStatus);
            AssertError(response.Data, "invalid_input", "Unknown CanvasDirector op 'dance'.");
        }

        [Fact]
        public void Dispatch_Extract_EnvelopeKeepsSnakeCaseUnderCamelCaseOptions()
        {
            var response = new CanvasDirectorHandler(new FakeExtractor()).Dispatch("{\"op\":\"extract\"}");

            Assert.True(response.Success);
            Assert.Equal(200, response.HttpStatus);

            var json = JsonSerializer.Serialize(
                response.Data,
                new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase });

            Assert.Contains("\"canvas_export_state\":", json);
            Assert.Contains("\"canvas_export_state_sha256\":", json);
            Assert.Contains("\"read_only\":", json);
            Assert.DoesNotContain("canvasExportState", json);
            Assert.DoesNotContain("canvasExportStateSha256", json);
        }

        [Fact]
        public void Sha256Hex_IsStableForSortedKeys()
        {
            using var first = JsonDocument.Parse("{\"b\":\"2\",\"a\":\"1\"}");
            using var second = JsonDocument.Parse("{\"a\":\"1\",\"b\":\"2\"}");

            Assert.Equal(
                CanvasDirectorCanonicalJson.Sha256Hex(first.RootElement),
                CanvasDirectorCanonicalJson.Sha256Hex(second.RootElement));
        }

        [Theory]
        [InlineData("{\"b\":\"2\",\"a\":\"1\"}", "{\"a\":\"1\",\"b\":\"2\"}")]
        [InlineData("{\"text\":\"<>&\",\"list\":[true,null,3]}", "{\"list\":[true,null,3],\"text\":\"<>&\"}")]
        public void Serialize_UsesCanonicalSerializationVectors(string input, string expected)
        {
            using var document = JsonDocument.Parse(input);

            Assert.Equal(expected, CanvasDirectorCanonicalJson.Serialize(document.RootElement));
        }

        [Fact]
        public void Serialize_RejectsNonIntegerNumbersInSliceOne()
        {
            using var document = JsonDocument.Parse("{\"value\":1.25}");

            var ex = Assert.Throws<CanvasDirectorException>(
                () => CanvasDirectorCanonicalJson.Serialize(document.RootElement));
            Assert.Equal("invalid_input", ex.Code);
        }

        [Fact]
        public void Serialize_RejectsNonAsciiObjectKeysInSliceOne()
        {
            using var document = JsonDocument.Parse("{\"\uD83D\uDE00\":1}");

            var ex = Assert.Throws<CanvasDirectorException>(
                () => CanvasDirectorCanonicalJson.Serialize(document.RootElement));
            Assert.Equal("invalid_input", ex.Code);
            Assert.Contains("object keys must be ASCII", ex.Message);
        }

        [Fact]
        public void Parse_PreservesDocumentIdAndProposalId()
        {
            var request = CanvasDirectorExtractRequest.Parse(
                "{\"op\":\"extract\",\"document_id\":\"doc_a\",\"proposal_id\":\"proposal_b\"}");

            Assert.Equal("doc_a", request.DocumentId);
            Assert.Equal("proposal_b", request.ProposalId);
        }

        [Theory]
        [InlineData("{\"op\":\"extract\",\"document_id\":123}", "document_id")]
        [InlineData("{\"op\":\"extract\",\"proposal_id\":false}", "proposal_id")]
        [InlineData("{\"op\":\"extract\",\"export_id\":{}}", "export_id")]
        [InlineData("{\"op\":\"extract\",\"solve_mode\":7}", "solve_mode")]
        [InlineData("{\"op\":\"extract\",\"expected_solution_token\":[]}", "expected_solution_token")]
        public void Dispatch_Extract_RejectsPresentNonStringRequestFields(
            string requestJson,
            string fieldName)
        {
            var response = new CanvasDirectorHandler(new FakeExtractor()).Dispatch(requestJson);

            Assert.False(response.Success);
            Assert.Equal(400, response.HttpStatus);
            AssertError(response.Data, "invalid_input", $"{fieldName} must be a string");
        }

        private static void AssertError(object? data, string expectedCode, string expectedMessagePart)
        {
            Assert.NotNull(data);
            var type = data!.GetType();
            Assert.Equal(expectedCode, type.GetProperty("code")?.GetValue(data));
            var message = Assert.IsType<string>(type.GetProperty("message")?.GetValue(data));
            Assert.Contains(expectedMessagePart, message);
        }

        private sealed class FakeExtractor : ICanvasDirectorExtractor
        {
            public CanvasDirectorExtractionEnvelope Extract(CanvasDirectorExtractRequest request)
            {
                return CanvasDirectorExtractionEnvelope.FromState(new
                {
                    schema_version = 1,
                    export_id = request.ExportId ?? "export_a",
                    template_id = "canvas_director.basic_motion",
                    template_version = "0.1.0",
                    payload = new
                    {
                        timeline = new
                        {
                            fps = 24,
                            frame_count = 3,
                        },
                    },
                });
            }
        }
    }
}
