using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Rook.Handlers;
using Rook.Services.Vision.MediaImport;
using Xunit;

namespace Rook.Tests.Handlers
{
    public class MediaImportOpHandlerTests
    {
        [Fact]
        public void DispatchUi_StartWithEmptySelection_ReturnsNeutralSuccess()
        {
            using var manager = NewManager();
            var handler = new MediaImportOpHandler(
                manager,
                new FakePicker(Array.Empty<string>()));

            var response = handler.DispatchUi("""{"op":"start_media_import"}""");

            AssertOk(response);
            var data = AssertDataDict(response);
            Assert.Equal(false, data["created"]);
            Assert.Equal("empty_selection", data["reason"]);
        }

        [Fact]
        public void DispatchUi_Start_ReturnsBasenamesWithoutLocalPaths()
        {
            using var manager = NewManager();
            var handler = new MediaImportOpHandler(
                manager,
                new FakePicker(new[]
                {
                    @"C:\secret\site-photo.png",
                    @"D:\private\clip.mp4",
                }));

            var response = handler.DispatchUi("""{"op":"start_media_import"}""");

            AssertOk(response);
            var payload = JsonSerializer.Serialize(response.Data);
            Assert.DoesNotContain(@"C:\secret", payload);
            Assert.DoesNotContain(@"D:\private", payload);

            var data = AssertDataDict(response);
            Assert.Equal(true, data["created"]);
            Assert.NotNull(data["job_id"]);
            Assert.Equal("queued", data["state"]);
            var files = Assert.IsType<List<Dictionary<string, object?>>>(data["files"]);
            Assert.Equal(new[] { "site-photo.png", "clip.mp4" },
                files.Select(row => Assert.IsType<string>(row["basename"])).ToArray());
            Assert.All(files, row =>
            {
                Assert.True(row.ContainsKey("import_item_id"));
                Assert.True(row.ContainsKey("status"));
                Assert.False(row.ContainsKey("path"));
            });
        }

        [Fact]
        public void DispatchUi_StartWithTooManyFiles_ReturnsStartLevelFailure()
        {
            using var manager = NewManager();
            var paths = Enumerable.Range(0, MediaImportConstants.MaxBatchFiles + 1)
                .Select(i => $@"C:\media\{i}.png")
                .ToArray();
            var handler = new MediaImportOpHandler(manager, new FakePicker(paths));

            var response = handler.DispatchUi("""{"op":"start_media_import"}""");

            Assert.False(response.Success);
            Assert.Equal(400, response.HttpStatus);
            var payload = JsonSerializer.Serialize(response.Data);
            Assert.Contains("too_many_files", payload);
        }

        [Fact]
        public async Task DispatchOffUi_StatusAndList_SerializeSnapshots()
        {
            var artifactId = Guid.Parse("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
            using var manager = NewManager(new FakeProcessor
            {
                Result = MediaImportProcessResult.Success(
                    artifactId,
                    MediaImportConstants.ImportedImageKind),
            });
            var handler = new MediaImportOpHandler(
                manager,
                new FakePicker(new[] { @"C:\media\a.png" }));

            var start = handler.DispatchUi("""{"op":"start_media_import"}""");
            var jobId = Assert.IsType<string>(AssertDataDict(start)["job_id"]);
            await WaitForTerminal(manager, Guid.Parse(jobId));

            var status = handler.DispatchOffUi(
                $$"""{"op":"get_media_import_job","job_id":"{{jobId}}"}""");
            AssertOk(status);
            var statusData = AssertDataDict(status);
            Assert.Equal(jobId, statusData["job_id"]);
            Assert.Equal("complete", statusData["state"]);
            var files = Assert.IsType<List<Dictionary<string, object?>>>(statusData["files"]);
            var file = Assert.Single(files);
            Assert.Equal("a.png", file["basename"]);
            Assert.Equal("imported", file["status"]);
            Assert.Equal(artifactId.ToString("D"), file["artifact_id"]);
            Assert.Equal("imported_image", file["artifact_kind"]);
            Assert.False(file.ContainsKey("path"));

            var list = handler.DispatchOffUi("""{"op":"list_media_import_jobs"}""");
            AssertOk(list);
            var jobs = Assert.IsType<List<Dictionary<string, object?>>>(
                AssertDataDict(list)["jobs"]);
            Assert.Contains(jobs, row => Equals(jobId, row["job_id"]));
        }

        [Fact]
        public void DispatchOffUi_Start_ReturnsRoutingMisuseFailure()
        {
            using var manager = NewManager();
            var handler = new MediaImportOpHandler(
                manager,
                new FakePicker(new[] { @"C:\media\a.png" }));

            var response = handler.DispatchOffUi("""{"op":"start_media_import"}""");

            Assert.False(response.Success);
            Assert.Equal(400, response.HttpStatus);
            Assert.Contains("UI dispatcher", JsonSerializer.Serialize(response.Data));
        }

        private static MediaImportJobManager NewManager(
            IMediaImportProcessor? processor = null) =>
            new(processor ?? new FakeProcessor());

        private static async Task WaitForTerminal(
            MediaImportJobManager manager,
            Guid jobId)
        {
            var deadline = DateTime.UtcNow.AddSeconds(5);
            while (DateTime.UtcNow < deadline)
            {
                var snapshot = manager.GetJob(jobId);
                if (snapshot?.State == MediaImportJobState.Complete)
                    return;
                await Task.Delay(20).ConfigureAwait(false);
            }
            throw new TimeoutException("Media import job did not complete.");
        }

        private static void AssertOk(ApiResponse response)
        {
            Assert.True(
                response.Success,
                "expected success=true; data: " +
                JsonSerializer.Serialize(response.Data));
            Assert.Equal(200, response.HttpStatus);
        }

        private static Dictionary<string, object?> AssertDataDict(
            ApiResponse response)
        {
            Assert.NotNull(response.Data);
            var dict = response.Data as Dictionary<string, object?>;
            Assert.NotNull(dict);
            return dict!;
        }

        private sealed class FakePicker : IMediaImportPicker
        {
            private readonly IReadOnlyList<string> _paths;

            public FakePicker(IReadOnlyList<string> paths)
            {
                _paths = paths;
            }

            public IReadOnlyList<string> PickFiles() => _paths;
        }

        private sealed class FakeProcessor : IMediaImportProcessor
        {
            public MediaImportProcessResult Result { get; set; } =
                MediaImportProcessResult.Success(
                    Guid.Parse("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
                    MediaImportConstants.ImportedImageKind);

            public Task<MediaImportProcessResult> ProcessAsync(
                string path,
                CancellationToken ct) =>
                Task.FromResult(Result);
        }
    }
}
