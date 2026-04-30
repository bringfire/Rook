using System;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Replicate;
using Xunit;

namespace Rook.Tests.Services.Vision.Replicate
{
    public class ReplicateLifecycleMapperTests
    {
        [Fact]
        public void ParseSubmitHandle_reads_id_urls_and_metadata_without_response_url_or_logs()
        {
            var json = JsonNode.Parse("""
                {
                  "id": "pred-1",
                  "status": "starting",
                  "model": "black-forest-labs/flux-schnell",
                  "version": "abc123",
                  "logs": "prompt and debug log",
                  "urls": {
                    "get": "https://api.replicate.com/v1/predictions/pred-1",
                    "cancel": "https://api.replicate.com/v1/predictions/pred-1/cancel"
                  }
                }
                """)!;

            var handle = ReplicateLifecycleMapper.ParseSubmitHandle(json);

            Assert.Equal("pred-1", handle.ProviderJobId);
            Assert.Equal("https://api.replicate.com/v1/predictions/pred-1", handle.StatusUrl!.ToString());
            Assert.Null(handle.ResponseUrl);
            Assert.Equal("https://api.replicate.com/v1/predictions/pred-1/cancel", handle.CancelUrl!.ToString());
            Assert.Equal("POST", handle.CancelHttpMethod);
            Assert.Null(handle.ProviderResultToken);
            Assert.Equal("black-forest-labs/flux-schnell", handle.ProviderMetadata!["model"]!.GetValue<string>());
            Assert.Equal("abc123", handle.ProviderMetadata["version"]!.GetValue<string>());
            Assert.True(handle.ProviderMetadata.ContainsKey("urls"));
            Assert.False(handle.ProviderMetadata.ContainsKey("logs"));
        }

        [Fact]
        public void ParseSubmitHandle_rejects_missing_id()
        {
            var json = JsonNode.Parse("""{ "status": "starting" }""")!;

            var ex = Assert.Throws<ArgumentException>(
                () => ReplicateLifecycleMapper.ParseSubmitHandle(json));

            Assert.Contains("id", ex.Message);
        }

        [Theory]
        [InlineData("starting", GenerationLifecycleState.Pending)]
        [InlineData("processing", GenerationLifecycleState.Running)]
        public void MapStatus_maps_in_flight_states(string status, GenerationLifecycleState state)
        {
            var handle = new ProviderJobHandle("pred-1");
            var json = JsonNode.Parse($$"""
                { "id": "pred-1", "status": "{{status}}" }
                """)!;

            var outcome = ReplicateLifecycleMapper.MapStatus(handle, json);

            var inFlight = Assert.IsType<InFlightStatusOutcome>(outcome);
            Assert.Equal(state, inFlight.State);
            Assert.Null(inFlight.Progress);
        }

        [Fact]
        public void MapStatus_succeeded_with_single_url_string_stamps_result_token_and_preserves_output()
        {
            var handle = new ProviderJobHandle("pred-1");
            var json = JsonNode.Parse("""
                {
                  "id": "pred-1",
                  "status": "succeeded",
                  "output": "https://replicate.delivery/pbxt/output.png",
                  "metrics": { "predict_time": 0.507, "total_time": 0.543 },
                  "model": "black-forest-labs/flux-schnell",
                  "version": "abc123",
                  "data_removed": false,
                  "urls": {
                    "get": "https://api.replicate.com/v1/predictions/pred-1",
                    "cancel": "https://api.replicate.com/v1/predictions/pred-1/cancel"
                  },
                  "logs": "do not persist this by default"
                }
                """)!;

            var outcome = ReplicateLifecycleMapper.MapStatus(handle, json);

            var complete = Assert.IsType<ProviderCompleteStatusOutcome>(outcome);
            Assert.Equal("pred-1", complete.UpdatedHandle.ProviderJobId);
            Assert.Equal("https://api.replicate.com/v1/predictions/pred-1", complete.UpdatedHandle.StatusUrl!.ToString());
            Assert.Null(complete.UpdatedHandle.ResponseUrl);
            Assert.Equal("https://api.replicate.com/v1/predictions/pred-1/cancel", complete.UpdatedHandle.CancelUrl!.ToString());
            Assert.Equal("POST", complete.UpdatedHandle.CancelHttpMethod);
            Assert.Equal("https://replicate.delivery/pbxt/output.png", complete.UpdatedHandle.ProviderResultToken);
            Assert.Equal("https://replicate.delivery/pbxt/output.png", complete.UpdatedHandle.ProviderMetadata!["output"]!.GetValue<string>());
            Assert.Equal(0.507, complete.UpdatedHandle.ProviderMetadata["metrics"]!["predict_time"]!.GetValue<double>());
            Assert.False(complete.UpdatedHandle.ProviderMetadata.ContainsKey("logs"));
        }

        [Fact]
        public void MapStatus_succeeded_with_single_item_url_array_stamps_result_token_and_preserves_array()
        {
            var handle = new ProviderJobHandle("pred-1");
            var json = JsonNode.Parse("""
                {
                  "id": "pred-1",
                  "status": "succeeded",
                  "output": [ "https://replicate.delivery/pbxt/output.png" ]
                }
                """)!;

            var outcome = ReplicateLifecycleMapper.MapStatus(handle, json);

            var complete = Assert.IsType<ProviderCompleteStatusOutcome>(outcome);
            Assert.Equal("https://replicate.delivery/pbxt/output.png", complete.UpdatedHandle.ProviderResultToken);
            var output = Assert.IsType<JsonArray>(complete.UpdatedHandle.ProviderMetadata!["output"]);
            Assert.Single(output);
        }

        [Fact]
        public void MapStatus_succeeded_with_multi_item_output_preserves_cardinality_without_result_token()
        {
            var handle = new ProviderJobHandle("pred-1");
            var json = JsonNode.Parse("""
                {
                  "id": "pred-1",
                  "status": "succeeded",
                  "output": [
                    "https://replicate.delivery/pbxt/one.png",
                    "https://replicate.delivery/pbxt/two.png"
                  ]
                }
                """)!;

            var outcome = ReplicateLifecycleMapper.MapStatus(handle, json);

            var complete = Assert.IsType<ProviderCompleteStatusOutcome>(outcome);
            Assert.Null(complete.UpdatedHandle.ProviderResultToken);
            var output = Assert.IsType<JsonArray>(complete.UpdatedHandle.ProviderMetadata!["output"]);
            Assert.Equal(2, output.Count);
        }

        [Fact]
        public void MapStatus_succeeded_with_object_output_preserves_output_without_result_token()
        {
            var handle = new ProviderJobHandle("pred-1");
            var json = JsonNode.Parse("""
                {
                  "id": "pred-1",
                  "status": "succeeded",
                  "output": { "images": [ "https://replicate.delivery/pbxt/output.png" ] }
                }
                """)!;

            var outcome = ReplicateLifecycleMapper.MapStatus(handle, json);

            var complete = Assert.IsType<ProviderCompleteStatusOutcome>(outcome);
            Assert.Null(complete.UpdatedHandle.ProviderResultToken);
            Assert.IsType<JsonObject>(complete.UpdatedHandle.ProviderMetadata!["output"]);
        }

        [Fact]
        public void MapStatus_data_removed_true_returns_dependency_unavailable()
        {
            var handle = new ProviderJobHandle("pred-1");
            var json = JsonNode.Parse("""
                {
                  "id": "pred-1",
                  "status": "succeeded",
                  "output": null,
                  "data_removed": true
                }
                """)!;

            var outcome = ReplicateLifecycleMapper.MapStatus(handle, json);

            var failed = Assert.IsType<FailedStatusOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
            Assert.Contains("provider output expired before Rook copied it", failed.Error.Message);
        }

        [Theory]
        [InlineData("failed")]
        [InlineData("canceled")]
        public void MapStatus_data_removed_true_returns_dependency_unavailable_regardless_of_terminal_status(
            string status)
        {
            var handle = new ProviderJobHandle("pred-1");
            var json = JsonNode.Parse($$"""
                {
                  "id": "pred-1",
                  "status": "{{status}}",
                  "error": "removed",
                  "data_removed": true
                }
                """)!;

            var outcome = ReplicateLifecycleMapper.MapStatus(handle, json);

            var failed = Assert.IsType<FailedStatusOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
            Assert.Equal("data_removed", failed.Error.ProviderErrorCode);
            Assert.Contains("provider output expired before Rook copied it", failed.Error.Message);
        }

        [Fact]
        public void MapStatus_mismatched_id_returns_execution_failed_without_completing()
        {
            var handle = new ProviderJobHandle("pred-1");
            var json = JsonNode.Parse("""
                {
                  "id": "pred-2",
                  "status": "succeeded",
                  "output": "https://replicate.delivery/pbxt/output.png"
                }
                """)!;

            var outcome = ReplicateLifecycleMapper.MapStatus(handle, json);

            var failed = Assert.IsType<FailedStatusOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
            Assert.Contains("did not match", failed.Error.Message);
        }

        [Fact]
        public void MapStatus_succeeded_with_malformed_refresh_url_returns_execution_failed()
        {
            var handle = new ProviderJobHandle(
                "pred-1",
                statusUrl: new Uri("https://api.replicate.com/v1/predictions/pred-1"),
                cancelUrl: new Uri("https://api.replicate.com/v1/predictions/pred-1/cancel"),
                cancelHttpMethod: "POST");
            var json = JsonNode.Parse("""
                {
                  "id": "pred-1",
                  "status": "succeeded",
                  "output": "https://replicate.delivery/pbxt/output.png",
                  "urls": {
                    "get": "not a url",
                    "cancel": "https://api.replicate.com/v1/predictions/pred-1/cancel"
                  }
                }
                """)!;

            var outcome = ReplicateLifecycleMapper.MapStatus(handle, json);

            var failed = Assert.IsType<FailedStatusOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
            Assert.Contains("urls.get", failed.Error.Message);
        }

        [Theory]
        [InlineData("get", "ftp://api.replicate.com/v1/predictions/pred-1")]
        [InlineData("get", "file:///C:/temp/prediction.json")]
        [InlineData("cancel", "ftp://api.replicate.com/v1/predictions/pred-1/cancel")]
        [InlineData("cancel", "file:///C:/temp/cancel")]
        public void MapStatus_succeeded_with_unsupported_refresh_url_scheme_returns_execution_failed(
            string urlField,
            string url)
        {
            var handle = new ProviderJobHandle(
                "pred-1",
                statusUrl: new Uri("https://api.replicate.com/v1/predictions/pred-1"),
                cancelUrl: new Uri("https://api.replicate.com/v1/predictions/pred-1/cancel"),
                cancelHttpMethod: "POST");
            var getUrl = urlField == "get"
                ? url
                : "https://api.replicate.com/v1/predictions/pred-1";
            var cancelUrl = urlField == "cancel"
                ? url
                : "https://api.replicate.com/v1/predictions/pred-1/cancel";
            var json = JsonNode.Parse($$"""
                {
                  "id": "pred-1",
                  "status": "succeeded",
                  "output": "https://replicate.delivery/pbxt/output.png",
                  "urls": {
                    "get": "{{getUrl}}",
                    "cancel": "{{cancelUrl}}"
                  }
                }
                """)!;

            var outcome = ReplicateLifecycleMapper.MapStatus(handle, json);

            var failed = Assert.IsType<FailedStatusOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
            Assert.Equal("malformed_urls", failed.Error.ProviderErrorCode);
            Assert.Contains($"urls.{urlField}", failed.Error.Message);
        }

        [Fact]
        public void MapStatus_succeeded_with_null_output_without_data_removed_returns_execution_failed()
        {
            var handle = new ProviderJobHandle("pred-1");
            var json = JsonNode.Parse("""
                {
                  "id": "pred-1",
                  "status": "succeeded",
                  "output": null,
                  "data_removed": false
                }
                """)!;

            var outcome = ReplicateLifecycleMapper.MapStatus(handle, json);

            var failed = Assert.IsType<FailedStatusOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
        }

        [Fact]
        public void MapStatus_failed_maps_replicate_error_as_non_retryable_execution_failed()
        {
            var handle = new ProviderJobHandle("pred-1");
            var json = JsonNode.Parse("""
                {
                  "id": "pred-1",
                  "status": "failed",
                  "error": "model execution failed"
                }
                """)!;

            var outcome = ReplicateLifecycleMapper.MapStatus(handle, json);

            var failed = Assert.IsType<FailedStatusOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
            Assert.Equal("failed", failed.Error.ProviderErrorCode);
            Assert.Contains("model execution failed", failed.Error.Message);
            Assert.Equal("model execution failed", failed.Error.ProviderDetail!["error"]!.GetValue<string>());
        }

        [Fact]
        public void MapStatus_failed_with_obvious_dependency_error_maps_dependency_unavailable()
        {
            var handle = new ProviderJobHandle("pred-1");
            var json = JsonNode.Parse("""
                {
                  "id": "pred-1",
                  "status": "failed",
                  "error": "network timeout while fetching model weights"
                }
                """)!;

            var outcome = ReplicateLifecycleMapper.MapStatus(handle, json);

            var failed = Assert.IsType<FailedStatusOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
            Assert.Equal("failed", failed.Error.ProviderErrorCode);
            Assert.Contains("network timeout", failed.Error.Message);
        }

        [Fact]
        public void MapStatus_canceled_maps_distinct_non_retryable_cancelled_error()
        {
            var handle = new ProviderJobHandle("pred-1");
            var json = JsonNode.Parse("""
                {
                  "id": "pred-1",
                  "status": "canceled",
                  "error": "user canceled"
                }
                """)!;

            var outcome = ReplicateLifecycleMapper.MapStatus(handle, json);

            var failed = Assert.IsType<FailedStatusOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.Cancelled, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
            Assert.Equal("canceled", failed.Error.ProviderErrorCode);
            Assert.Contains("cancel", failed.Error.Message, StringComparison.OrdinalIgnoreCase);
        }

        [Theory]
        [InlineData("""{ "id": "pred-1" }""")]
        [InlineData("""{ "id": "pred-1", "status": "queued" }""")]
        [InlineData("""{ "id": "pred-1", "status": 200 }""")]
        public void MapStatus_missing_unknown_or_malformed_status_returns_execution_failed(string body)
        {
            var handle = new ProviderJobHandle("pred-1");
            var json = JsonNode.Parse(body)!;

            var outcome = ReplicateLifecycleMapper.MapStatus(handle, json);

            var failed = Assert.IsType<FailedStatusOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
        }

        [Fact]
        public void MapStatus_non_object_status_body_returns_execution_failed()
        {
            var handle = new ProviderJobHandle("pred-1");
            var json = JsonValue.Create("not an object")!;

            var outcome = ReplicateLifecycleMapper.MapStatus(handle, json);

            var failed = Assert.IsType<FailedStatusOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
        }
    }
}
