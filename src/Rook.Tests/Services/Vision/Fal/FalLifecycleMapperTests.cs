using System;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Fal
{
    public class FalLifecycleMapperTests
    {
        [Fact]
        public void ParseSubmitHandle_reads_queue_urls_and_cancel_method()
        {
            var json = JsonNode.Parse("""
                {
                  "request_id": "abc123",
                  "status": "IN_QUEUE",
                  "status_url": "https://queue.fal.run/status/abc123",
                  "response_url": "https://queue.fal.run/response/abc123",
                  "cancel_url": "https://queue.fal.run/cancel/abc123",
                  "queue_position": 3
                }
                """)!;

            var handle = FalLifecycleMapper.ParseSubmitHandle(json, "PUT");

            Assert.Equal("abc123", handle.ProviderJobId);
            Assert.Equal("https://queue.fal.run/status/abc123", handle.StatusUrl!.ToString());
            Assert.Equal("https://queue.fal.run/response/abc123", handle.ResponseUrl!.ToString());
            Assert.Equal("https://queue.fal.run/cancel/abc123", handle.CancelUrl!.ToString());
            Assert.Equal("PUT", handle.CancelHttpMethod);
            Assert.Equal(3, handle.ProviderMetadata!["queue_position"]!.GetValue<int>());
        }

        [Theory]
        [InlineData("IN_QUEUE", typeof(InFlightStatusOutcome), GenerationLifecycleState.Pending)]
        [InlineData("IN_PROGRESS", typeof(InFlightStatusOutcome), GenerationLifecycleState.Running)]
        [InlineData("COMPLETED", typeof(ProviderCompleteStatusOutcome), GenerationLifecycleState.Completed)]
        public void MapStatus_maps_fal_states(string rawState, Type expectedType, GenerationLifecycleState expectedState)
        {
            var handle = new ProviderJobHandle("abc123");
            var json = JsonNode.Parse($$"""
                {
                  "request_id": "abc123",
                  "status": "{{rawState}}",
                  "queue_position": 1
                }
                """)!;

            var outcome = FalLifecycleMapper.MapStatus(handle, json);

            Assert.IsType(expectedType, outcome);
            if (outcome is InFlightStatusOutcome inFlight)
                Assert.Equal(expectedState, inFlight.State);
        }

        [Fact]
        public void MapStatus_unknown_state_returns_failed_status()
        {
            var handle = new ProviderJobHandle("abc123");
            var json = JsonNode.Parse("""
                { "request_id": "abc123", "status": "TOTALLY_NEW" }
                """)!;

            var outcome = FalLifecycleMapper.MapStatus(handle, json);

            var failed = Assert.IsType<FailedStatusOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.Contains("Unknown fal lifecycle state", failed.Error.Message);
        }
    }
}
