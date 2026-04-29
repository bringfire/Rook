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

        [Fact]
        public void ParseSubmitHandle_rejects_non_object_submit_body()
        {
            var json = JsonValue.Create("not an object")!;

            var ex = Assert.Throws<ArgumentException>(
                () => FalLifecycleMapper.ParseSubmitHandle(json, "PUT"));

            Assert.Equal("submitBody", ex.ParamName);
        }

        [Fact]
        public void ParseSubmitHandle_rejects_missing_request_id()
        {
            var json = new JsonObject();

            var ex = Assert.Throws<ArgumentException>(
                () => FalLifecycleMapper.ParseSubmitHandle(json, "PUT"));

            Assert.Contains("request_id", ex.Message);
        }

        [Theory]
        [InlineData("")]
        [InlineData("   ")]
        public void ParseSubmitHandle_rejects_blank_request_id(string requestId)
        {
            var json = new JsonObject { ["request_id"] = requestId };

            var ex = Assert.Throws<ArgumentException>(
                () => FalLifecycleMapper.ParseSubmitHandle(json, "PUT"));

            Assert.Contains("request_id", ex.Message);
        }

        [Fact]
        public void ParseSubmitHandle_clones_status_and_queue_position_metadata()
        {
            var status = new JsonObject { ["state"] = "IN_QUEUE" };
            var json = new JsonObject
            {
                ["request_id"] = "abc123",
                ["status"] = status,
                ["queue_position"] = 3,
            };

            var handle = FalLifecycleMapper.ParseSubmitHandle(json, "PUT");
            status["state"] = "IN_PROGRESS";
            json["queue_position"] = 9;

            Assert.Equal("IN_QUEUE", handle.ProviderMetadata!["status"]!["state"]!.GetValue<string>());
            Assert.Equal(3, handle.ProviderMetadata["queue_position"]!.GetValue<int>());
        }

        [Theory]
        [InlineData("IN_QUEUE", typeof(InFlightStatusOutcome), GenerationLifecycleState.Pending)]
        [InlineData("IN_PROGRESS", typeof(InFlightStatusOutcome), GenerationLifecycleState.Running)]
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
            {
                Assert.Equal(expectedState, inFlight.State);
                Assert.Equal(1, inFlight.Progress!.QueuePosition);
            }
        }

        [Fact]
        public void MapStatus_null_handle_throws()
        {
            var json = JsonNode.Parse("""
                { "request_id": "abc123", "status": "IN_QUEUE" }
                """)!;

            Assert.Throws<ArgumentNullException>(
                () => FalLifecycleMapper.MapStatus(null!, json));
        }

        [Fact]
        public void MapStatus_non_object_status_body_returns_failed_status()
        {
            var handle = new ProviderJobHandle("abc123");
            var json = JsonValue.Create("not an object")!;

            var outcome = FalLifecycleMapper.MapStatus(handle, json);

            var failed = Assert.IsType<FailedStatusOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
        }

        [Fact]
        public void MapStatus_missing_status_returns_failed_status()
        {
            var handle = new ProviderJobHandle("abc123");
            var json = JsonNode.Parse("""
                { "request_id": "abc123" }
                """)!;

            var outcome = FalLifecycleMapper.MapStatus(handle, json);

            var failed = Assert.IsType<FailedStatusOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.Contains("Unknown fal lifecycle state", failed.Error.Message);
        }

        [Fact]
        public void MapStatus_whitespace_status_returns_failed_status()
        {
            var handle = new ProviderJobHandle("abc123");
            var json = JsonNode.Parse("""
                { "request_id": "abc123", "status": "   " }
                """)!;

            var outcome = FalLifecycleMapper.MapStatus(handle, json);

            var failed = Assert.IsType<FailedStatusOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.Contains("Unknown fal lifecycle state", failed.Error.Message);
        }

        [Fact]
        public void MapStatus_in_flight_allows_absent_queue_position()
        {
            var handle = new ProviderJobHandle("abc123");
            var json = JsonNode.Parse("""
                { "request_id": "abc123", "status": "IN_QUEUE" }
                """)!;

            var outcome = FalLifecycleMapper.MapStatus(handle, json);

            var inFlight = Assert.IsType<InFlightStatusOutcome>(outcome);
            Assert.Equal(GenerationLifecycleState.Pending, inFlight.State);
            Assert.Null(inFlight.Progress);
        }

        [Fact]
        public void MapStatus_completed_returns_same_handle()
        {
            var handle = new ProviderJobHandle("abc123");
            var json = JsonNode.Parse("""
                {
                  "request_id": "abc123",
                  "status": "COMPLETED"
                }
                """)!;

            var outcome = FalLifecycleMapper.MapStatus(handle, json);

            var completed = Assert.IsType<ProviderCompleteStatusOutcome>(outcome);
            Assert.Same(handle, completed.UpdatedHandle);
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

        [Fact]
        public void MapStatus_non_string_status_returns_failed_status()
        {
            var handle = new ProviderJobHandle("abc123");
            var json = JsonNode.Parse("""
                { "request_id": "abc123", "status": 200 }
                """)!;

            var outcome = FalLifecycleMapper.MapStatus(handle, json);

            var failed = Assert.IsType<FailedStatusOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
            Assert.Contains("Unknown fal lifecycle state", failed.Error.Message);
            Assert.Null(failed.Error.ProviderErrorCode);
        }

        [Fact]
        public void MapStatus_non_int_queue_position_returns_failed_status()
        {
            var handle = new ProviderJobHandle("abc123");
            var json = JsonNode.Parse("""
                {
                  "request_id": "abc123",
                  "status": "IN_QUEUE",
                  "queue_position": "first"
                }
                """)!;

            var outcome = FalLifecycleMapper.MapStatus(handle, json);

            var failed = Assert.IsType<FailedStatusOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
            Assert.Equal("fal status body had invalid queue_position.", failed.Error.Message);
        }

        [Fact]
        public void MapStatus_null_queue_position_returns_failed_status()
        {
            var handle = new ProviderJobHandle("abc123");
            var json = JsonNode.Parse("""
                {
                  "request_id": "abc123",
                  "status": "IN_QUEUE",
                  "queue_position": null
                }
                """)!;

            var outcome = FalLifecycleMapper.MapStatus(handle, json);

            var failed = Assert.IsType<FailedStatusOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
            Assert.Equal("fal status body had invalid queue_position.", failed.Error.Message);
        }

        [Fact]
        public void MapStatus_negative_queue_position_returns_failed_status()
        {
            var handle = new ProviderJobHandle("abc123");
            var json = JsonNode.Parse("""
                {
                  "request_id": "abc123",
                  "status": "IN_QUEUE",
                  "queue_position": -1
                }
                """)!;

            var outcome = FalLifecycleMapper.MapStatus(handle, json);

            var failed = Assert.IsType<FailedStatusOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
            Assert.Equal("fal status body had invalid queue_position.", failed.Error.Message);
        }
    }
}
