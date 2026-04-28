using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Fixtures
{
    /// <summary>
    /// Captures byte-identity goldens for Veo's submit-time HTTP request
    /// body across five representative request shapes. Drives
    /// <see cref="VeoClient"/> through a scripted
    /// <see cref="TestHttpMessageHandler"/> that records the outgoing
    /// request body and returns a canned operation-name response so the
    /// rest of the V1c code path executes unmodified.
    ///
    /// <para>Goldens live at <c>Fixtures/Goldens/01_*.json</c> through
    /// <c>05_*.json</c> and are written via
    /// <see cref="VeoBehaviorParityFixture.AssertOrCapture"/> on first
    /// run; subsequent runs assert equality. Commits 2–5 must not change
    /// these bytes.</para>
    /// </summary>
    public class VeoSubmitEnvelopeCaptureTests
    {
        // 16 bytes of deterministic image content for I2V / Interp /
        // reference-image scenarios. Real Veo rejects sub-128px PNGs but
        // the capture probe never reaches Veo — TestHttpMessageHandler
        // intercepts before the network. Using a fixed buffer makes the
        // base64 encoding in the captured submit envelope stable across
        // runs.
        private static readonly byte[] FixedImageBytes =
            { 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
              0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52 };

        private const string FixedMimeType = "image/png";

        [Fact]
        public void Golden_01_t2v_veo_3_1_720p_8s()
        {
            var req = TestVideoFixtures.DefaultT2vRequest(
                model: "veo-3.1-generate-preview",
                duration: 8,
                resolution: "720p",
                prompt: "a cinematic shot of a coastline at dusk");

            var bodyJson = CaptureSubmitBody(req);
            VeoBehaviorParityFixture.AssertOrCapture(
                "01_t2v_veo_3_1_720p_8s_submit.json", bodyJson);
        }

        [Fact]
        public void Golden_02_t2v_veo_3_0_fast()
        {
            var req = TestVideoFixtures.DefaultT2vRequest(
                model: "veo-3.0-fast-generate-001",
                duration: 8,
                resolution: "1080p",
                prompt: "macro shot of dew on a leaf");

            var bodyJson = CaptureSubmitBody(req);
            VeoBehaviorParityFixture.AssertOrCapture(
                "02_t2v_veo_3_0_fast_submit.json", bodyJson);
        }

        [Fact]
        public void Golden_03_i2v_start_frame()
        {
            var startId = Guid.Parse("11111111-1111-1111-1111-111111111111");
            var req = TestVideoFixtures.DefaultT2vRequest(
                model: "veo-3.1-generate-preview",
                mode: VideoMode.I2V,
                duration: 8,
                resolution: "720p",
                prompt: "the scene comes alive",
                startFrame: MediaRef.ForArtifact(startId, "image"),
                personGeneration: PersonGenerationPolicy.AllowAdult);

            var resolved = ResolvedFor(req.StartFrame!);
            var bodyJson = CaptureSubmitBody(req, resolved);
            VeoBehaviorParityFixture.AssertOrCapture(
                "03_i2v_start_frame_submit.json", bodyJson);
        }

        [Fact]
        public void Golden_04_frame_interpolation()
        {
            var startId = Guid.Parse("22222222-2222-2222-2222-222222222222");
            var endId = Guid.Parse("33333333-3333-3333-3333-333333333333");
            var req = TestVideoFixtures.DefaultT2vRequest(
                model: "veo-3.1-generate-preview",
                mode: VideoMode.Interp,
                duration: 8,
                resolution: "720p",
                prompt: "transition between the two frames",
                startFrame: MediaRef.ForArtifact(startId, "image"),
                endFrame: MediaRef.ForArtifact(endId, "image"),
                personGeneration: PersonGenerationPolicy.AllowAdult);

            var resolved = ResolvedFor(req.StartFrame!, req.EndFrame!);
            var bodyJson = CaptureSubmitBody(req, resolved);
            VeoBehaviorParityFixture.AssertOrCapture(
                "04_frame_interp_submit.json", bodyJson);
        }

        [Fact]
        public void Golden_05_t2v_with_reference_frames()
        {
            // Veo 3.1 (full) supports reference images; lite does not.
            var refIdA = Guid.Parse("44444444-4444-4444-4444-444444444444");
            var refIdB = Guid.Parse("55555555-5555-5555-5555-555555555555");
            var refs = new[]
            {
                MediaRef.ForArtifact(refIdA, "image"),
                MediaRef.ForArtifact(refIdB, "image"),
            };
            var req = TestVideoFixtures.DefaultT2vRequest(
                model: "veo-3.1-generate-preview",
                mode: VideoMode.T2V,
                duration: 8,
                resolution: "1080p",
                prompt: "a still life in the style of these references",
                referenceFrames: refs,
                seed: 12345,
                personGeneration: PersonGenerationPolicy.AllowAdult);

            var resolved = ResolvedFor(refs[0], refs[1]);
            var bodyJson = CaptureSubmitBody(req, resolved);
            VeoBehaviorParityFixture.AssertOrCapture(
                "05_t2v_refs_pg_seed_submit.json", bodyJson);
        }

        // ─── Capture helpers ─────────────────────────────────────────────

        private static string CaptureSubmitBody(
            VideoGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia>? resolved = null)
        {
            string? captured = null;

            var handler = new TestHttpMessageHandler
            {
                OnSend = req =>
                {
                    // ReadAsStringAsync is sync-safe inside the handler
                    // because StringContent buffers in memory.
                    captured = req.Content!
                        .ReadAsStringAsync().GetAwaiter().GetResult();
                    var resp = new HttpResponseMessage(HttpStatusCode.OK);
                    resp.Content = new StringContent(
                        "{\"name\":\"models/m/operations/op-capture\"}",
                        Encoding.UTF8, "application/json");
                    return resp;
                },
            };

            var client = new VeoClient(new HttpClient(handler));
            var options = (VeoOptions)request.Options;
            var media = resolved ?? new Dictionary<MediaRef, ResolvedMedia>();

            var task = client.StartGenerationAsync(
                "fake-api-key", request, options, media, CancellationToken.None);
            task.GetAwaiter().GetResult();

            Assert.NotNull(captured);
            return captured!;
        }

        private static IReadOnlyDictionary<MediaRef, ResolvedMedia>
            ResolvedFor(params MediaRef[] refs)
        {
            var dict = new Dictionary<MediaRef, ResolvedMedia>();
            foreach (var r in refs)
            {
                dict[r] = new ResolvedMedia(
                    Bytes: FixedImageBytes,
                    MimeType: FixedMimeType);
            }
            return dict;
        }
    }
}
