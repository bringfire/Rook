using System.Threading.Tasks;
using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Fal.Models;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Fal
{
    public class FalQuoteServiceTests
    {
        [Fact]
        public async Task Sequential_fixture_jobs_have_independent_owned_deadlines()
        {
            using var run = new FalConfiguredJobLifecycleTests.Run(false, sync: true);
            await run.Submit(); await FalConfiguredJobLifecycleTests.Wait(run.Terminal.Task);
            bool disposed = false;
            for (int i = 0; i < 100 && !disposed; i++)
            {
                try { _ = run.ImageDeadline.Token; await Task.Delay(10); }
                catch (ObjectDisposedException) { disposed = true; }
            }
            Assert.True(disposed, "The first job must settle its owned deadline before submitting the second job.");
            await run.Submit(); var second = run.Id;
            for (int i = 0; i < 100; i++)
            {
                var state = (await run.Image!.GetStatusAsync(second, default)).State;
                if (state is Rook.Services.Vision.Image.Jobs.ImageJobState.Complete or Rook.Services.Vision.Image.Jobs.ImageJobState.Error)
                { Assert.Equal(Rook.Services.Vision.Image.Jobs.ImageJobState.Complete, state); return; }
                await Task.Delay(10);
            }
            Assert.Fail("Second fixture job did not settle.");
        }

        [Fact]
        public void Unknown_history_projects_diagnostics_without_unvalidated_numeric_controls()
        {
            var raw = JsonNode.Parse("{\"version\":99,\"effective_request\":{\"seed\":9007199254740993},\"pricing\":{\"rate_usd\":0.12345678901234567890123456789}}")!.AsObject();
            var read = FalExecutionSnapshotCodec.Deserialize(raw);
            Assert.Null(read.Snapshot); Assert.NotNull(read.Diagnostic);
            Assert.False(read.PublicJson.ContainsKey("effective_request"));
            Assert.False(read.PublicJson.ContainsKey("pricing"));
            Assert.NotNull(read.Json["effective_request"]);
        }
        internal static FalMediaSnapshot Capture(FalNormalizedRequest r) => FalMediaSnapshot.Capture(r, new Dictionary<MediaRef, ResolvedMedia>(), new Rook.Services.Vision.Video.Framing.VideoPreparationResources());
        [Theory]
        [InlineData("0.00000001", "0.000001")] [InlineData("0.12345601", "0.123457")] [InlineData("0.123456", "0.123456")]
        public void Public_ceiling_rounds_up_and_keeps_internal_rate_exact(string rawRate, string rawCeiling)
        {
            using var files = new CatalogFiles(); var rate = decimal.Parse(rawRate, System.Globalization.CultureInfo.InvariantCulture);
            files.Operation["pricing"]!["rates"]![0]!["rate_usd"] = rate;
            var request = FalDeclarativePricingTests.Normalize(files); using var media = Capture(request);
            var quote = new FalQuoteService().Estimate(request, media).Quote!;
            Assert.Equal(rate, quote.Pricing.RateUsd); Assert.Equal(rate, quote.Pricing.EstimateMaxUsd);
            Assert.Equal(decimal.Parse(rawCeiling, System.Globalization.CultureInfo.InvariantCulture), quote.MaximumEstimatedCostUsd);
            Assert.Null(quote.ActualUsd); Assert.Null(quote.ToJson()["actual_usd"]);
            // JSON -> IEEE754 JavaScript number -> JSON -> submit retains the exposed cap.
            var wire = quote.ToJson();
            Assert.Equal(quote.Fingerprint, wire["quote_fingerprint"]!.GetValue<string>());
            Assert.False(wire.ContainsKey("estimate_fingerprint"));
            using var javascript = System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo("node",
                "-e \"process.stdout.write(JSON.stringify(JSON.parse(require('fs').readFileSync(0,'utf8'))))\"")
                { UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true })!;
            javascript.StandardInput.Write(wire.ToJsonString()); javascript.StandardInput.Close();
            var roundTrip = javascript.StandardOutput.ReadToEnd(); Assert.True(javascript.WaitForExit(5000)); Assert.Equal(0, javascript.ExitCode);
            Assert.Null(FalSubmitConfirmation.TryParse(JsonNode.Parse(roundTrip)!.AsObject(), out var confirmation));
            Assert.Null(new FalQuoteService().Validate(quote, request, media, confirmation));
            Assert.Single(wire["candidates"]!.AsArray());
        }
        [Theory]
        [InlineData("request")] [InlineData("options")] [InlineData("definition")]
        [InlineData("adapter")] [InlineData("endpoint")] [InlineData("pricing")]
        public void Any_changed_binding_controls_or_price_invalidates_quote(string change)
        {
            using var files = new CatalogFiles();
            var original = FalDeclarativePricingTests.Normalize(files); using var originalMedia = Capture(original);
            var service = new FalQuoteService(); var quote = service.Estimate(original, originalMedia).Quote!;
            JsonObject? fields = null, options = null;
            switch (change)
            {
                case "request": fields = new JsonObject { ["prompt"] = "changed" }; break;
                case "options": options = new JsonObject { ["strength"] = .2m }; break;
                case "definition": files.Definition["revision"] = "revision-2"; break;
                case "adapter": files.Operation["adapter"]!["version"] = 2; break;
                case "endpoint": files.Operation["endpoint_id"] = "fal-ai/synthetic/other"; break;
                case "pricing": files.Operation["pricing"]!["revision"] = "price-2"; break;
            }
            // Unsupported adapter versions are intentionally blocked by compiler; a changed valid
            // binding payload can still be compared without granting executable adapter authority.
            FalNormalizedRequest changed;
            if (change == "adapter")
            {
                var model = new FalModelDefinition(files.Definition, "synthetic");
                changed = new FalModelNormalizer().Normalize(model.Operations[0], original.SuppliedInput).Request!;
            }
            else changed = FalDeclarativePricingTests.Normalize(files, fields, options);
            using var changedMedia = Capture(changed);
            Assert.Equal("quote_stale", service.Validate(quote, changed, changedMedia, new FalSubmitConfirmation(quote.Fingerprint, quote.MaximumEstimatedCostUsd))!.ProviderErrorCode);
        }
        [Fact]
        public void Changed_artifact_bytes_invalidate_quote_and_original_bytes_are_frozen()
        {
            using var files = FalMediaPreparationTests.MediaFiles("data_uri");
            var compiled = files.Compile(); Assert.Empty(compiled.Diagnostics);
            var source = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var request = new FalModelNormalizer().Normalize(compiled.Catalog!.Definitions[0].Operations[0],
                new FalModelInput(new JsonObject { ["prompt"] = "draw" }, media: new[] { new FalMediaInput("primary_image", 0, source) })).Request!;
            var bytes = (byte[])FalMediaPreparationTests.Png.Clone(); var sources = new Dictionary<MediaRef, ResolvedMedia> { [source] = new(bytes, "image/png") };
            using var media = FalMediaSnapshot.Capture(request, sources, new Rook.Services.Vision.Video.Framing.VideoPreparationResources());
            var service = new FalQuoteService(); var quote = service.Estimate(request, media).Quote!;
            bytes[bytes.Length - 1] = 2;
            using var changed = FalMediaSnapshot.Capture(request, sources, new Rook.Services.Vision.Video.Framing.VideoPreparationResources());
            Assert.Equal("quote_stale", service.Validate(quote, request, changed, new FalSubmitConfirmation(quote.Fingerprint, quote.MaximumEstimatedCostUsd))!.ProviderErrorCode);
            Assert.Null(service.Validate(quote, request, media, new FalSubmitConfirmation(quote.Fingerprint, quote.MaximumEstimatedCostUsd)));
        }
        [Theory]
        [InlineData(.29, false)] [InlineData(.30, true)]
        public void Confirmation_caps_upper_bound(double cap, bool accepted)
        {
            using var files = new CatalogFiles(); var p = files.Operation["pricing"]!;
            p["strategy"] = "per_output_megapixel"; p["unit"] = "megapixel"; p["max_megapixels"] = 1.5m; p["rates"]![0]!["rate_usd"] = .2m;
            var request = FalDeclarativePricingTests.Normalize(files); using var media = Capture(request); var service = new FalQuoteService(); var q = service.Estimate(request, media).Quote!;
            Assert.Equal(accepted, service.Validate(q, request, media, new FalSubmitConfirmation(q.Fingerprint, (decimal)cap)) == null);
        }
        [Theory]
        [InlineData("\"0.1\"")] [InlineData("-1")] [InlineData("0.0000001")] [InlineData("0.12345600000000000000000000001")]
        [InlineData("1000000000.000001")] [InlineData("null")] [InlineData("true")]
        public void Untrusted_caps_fail_typed_before_decimal_conversion(string raw)
        {
            var wire = new JsonObject { ["quote_fingerprint"] = "fal1:" + new string('a', 64), ["max_estimated_cost_usd"] = JsonNode.Parse(raw) };
            Assert.NotNull(FalSubmitConfirmation.TryParse(wire, out var value)); Assert.Null(value);
        }
        [Theory]
        [InlineData(false)] [InlineData(true)]
        public async Task Configured_managers_require_confirmation_before_admission(bool video)
        {
            using var run = new FalConfiguredJobLifecycleTests.Run(video);
            var error = await run.SubmitUnconfirmed();
            Assert.NotNull(error);
            Assert.Equal("quote_confirmation_required", error!.ProviderErrorCode);
            Assert.Equal(0, run.Transport.Posts);
        }
        [Theory]
        [InlineData(false)] [InlineData(true)]
        public async Task Unconfirmed_pinned_admission_releases_transferred_media_owners(bool video)
        {
            using var run = new FalConfiguredJobLifecycleTests.Run(video); var normalized = run.Normalized();
            var resources = new Rook.Services.Vision.Video.Framing.VideoPreparationResources(maxBundles: 1);
            var media = FalMediaSnapshot.Capture(normalized, new Dictionary<MediaRef, ResolvedMedia>(), resources);
            Assert.Equal(1, resources.ActiveBundles);
            var options = new FalModelOptions(normalized.SuppliedInput, normalized.Binding.OperationId);
            GenerationError? error;
            if (video)
            {
                var shell = new Rook.Services.Vision.Video.VideoGenerationRequest(normalized.Binding.ModelId, Rook.Services.Vision.Video.VideoMode.T2V,
                    0, "placeholder", "placeholder", null, null, null, null, null, options, 1);
                error = (await run.Video!.SubmitConfiguredAsync(shell, normalized, media, null, System.Threading.CancellationToken.None)).GenerationError;
            }
            else
            {
                var shell = new Rook.Services.Vision.Image.ImageGenerationRequest(normalized.Binding.ModelId, "placeholder", "placeholder", "placeholder", 1, null, options);
                error = (await run.Image!.SubmitAsync(new Rook.Services.Vision.Image.Jobs.ImageJobStartRequest(shell,
                    new Dictionary<MediaRef, ResolvedMedia>(), Array.Empty<Guid>(), configuredRequest: normalized, configuredMedia: media), System.Threading.CancellationToken.None)).Error;
            }
            Assert.Equal("quote_confirmation_required", error!.ProviderErrorCode); Assert.Equal(0, resources.ActiveBundles); Assert.Equal(0, run.Transport.Posts);
        }
        [Theory]
        [InlineData("order")] [InlineData("identity")] [InlineData("source_role")] [InlineData("semantic_role")]
        public void Media_identity_order_and_both_roles_are_quote_inputs(string change)
        {
            using var files = FalMediaPreparationTests.MediaFiles("data_uri");
            var binding = files.Compile().Catalog!.Definitions[0].Operations[0];
            var a = MediaRef.ForArtifact(Guid.NewGuid(), "image"); var b = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var replacement = change == "source_role" ? MediaRef.ForArtifact(a.ArtifactId!.Value, "poster") : MediaRef.ForArtifact(Guid.NewGuid(), "image");
            FalNormalizedRequest Request(bool changed)
            {
                var primary = changed && change == "semantic_role" ? b : a;
                var first = changed && change == "order" ? b : changed && change is "identity" or "source_role" ? replacement : a;
                var second = changed && change == "order" ? a : b;
                return new FalModelNormalizer().Normalize(binding, new FalModelInput(new JsonObject { ["prompt"] = "draw" }, media: new[] {
                    new FalMediaInput("primary_image", 0, primary), new FalMediaInput("reference_image", 0, first), new FalMediaInput("reference_image", 1, second) })).Request!;
            }
            FalMediaSnapshot Snapshot(FalNormalizedRequest request)
            {
                var sources = new Dictionary<MediaRef, ResolvedMedia>();
                foreach (var m in request.Media) sources[m.Input.Source] = new ResolvedMedia(FalMediaPreparationTests.Png, "image/png");
                return FalMediaSnapshot.Capture(request, sources, new Rook.Services.Vision.Video.Framing.VideoPreparationResources());
            }
            var original = Request(false); using var media = Snapshot(original); var service = new FalQuoteService(); var quote = service.Estimate(original, media).Quote!;
            var changedRequest = Request(true); using var changedMedia = Snapshot(changedRequest);
            Assert.Equal("quote_stale", service.Validate(quote, changedRequest, changedMedia, new FalSubmitConfirmation(quote.Fingerprint, quote.MaximumEstimatedCostUsd))!.ProviderErrorCode);
        }
        [Theory]
        [InlineData(false)] [InlineData(true)]
        public async Task Artifact_pricing_is_lossless_public_text_while_durable_snapshot_stays_decimal(bool video)
        {
            using var run = new FalConfiguredJobLifecycleTests.Run(video, sync: !video, rate: .00000001m);
            run.Transport.Complete = true; run.Transport.FetchRelease.TrySetResult(true);
            await run.Submit(); await FalConfiguredJobLifecycleTests.Wait(run.Terminal.Task);
            var artifact = Assert.Single(run.Store.List()); var execution = artifact.Metadata[FalExecutionSnapshot.ExtensionKey]!;
            Assert.Equal(System.Text.Json.JsonValueKind.String, execution["pricing"]!["rate_usd"]!.GetValueKind());
            Assert.Equal("0.00000001", execution["binding"]!["operations"]![0]!["pricing"]!["rates"]![0]!["rate_usd"]!.GetValue<string>());
            Assert.Equal(.00000001m, run.Snapshot()!.Pricing!.RateUsd);
        }
        [Theory]
        [InlineData(false)] [InlineData(true)]
        public async Task Forged_low_pricing_cannot_authorize_dispatch(bool video)
        {
            using var run = new FalConfiguredJobLifecycleTests.Run(video);
            var forged = new FalPricingSnapshot("output", "forged", "forged", 0, 0, 0, 0, 0);
            var error = await run.AttemptConfirmed(0, forged);
            Assert.Equal("cost_cap_exceeded", error!.ProviderErrorCode); Assert.Equal(0, run.Transport.Posts);
            Assert.Null(await run.AttemptConfirmed(1m, forged));
            await FalConfiguredJobLifecycleTests.Wait(run.Transport.PollEntered.Task);
            Assert.Equal(video ? .55m : .01m, run.Snapshot()!.Pricing!.EstimateMaxUsd);
            Assert.Equal("price-1", run.Snapshot()!.Pricing!.Revision);
        }
        [Theory]
        [InlineData(false)] [InlineData(true)]
        public async Task Missing_pricing_or_stale_confirmation_never_dispatches(bool video)
        {
            using var missing = new FalConfiguredJobLifecycleTests.Run(video, pricingAvailable: false);
            Assert.Equal("pricing_unavailable", (await missing.AttemptConfirmed(1))!.ProviderErrorCode); Assert.Equal(0, missing.Transport.Posts);
            using var stale = new FalConfiguredJobLifecycleTests.Run(video);
            Assert.Equal("quote_stale", (await stale.AttemptConfirmed(1, fingerprint: "fal1:" + new string('0', 64)))!.ProviderErrorCode); Assert.Equal(0, stale.Transport.Posts);
        }
        [Fact]
        public async Task Values_changed_after_queue_admission_do_not_change_accepted_controls_or_price()
        {
            using var run = new FalConfiguredJobLifecycleTests.Run(false, sync: true); run.Transport.HoldSubmit = true;
            var normalized = run.Normalized();
            await run.Submit(normalized, Capture(normalized)); await run.Submit(normalized, Capture(normalized));
            var timer = System.Diagnostics.Stopwatch.StartNew();
            while (run.Transport.Posts < 2 && timer.ElapsedMilliseconds < 5000) await Task.Delay(10);
            Assert.Equal(2, run.Transport.Posts);
            await run.Submit(normalized, Capture(normalized)); var queued = run.Id;
            Assert.Equal(2, run.Transport.Posts);
            normalized.SuppliedInput.RequestFields["prompt"] = "mutated";
            normalized.EffectiveOptions["strength"] = .9m;
            run.Files.Operation["pricing"]!["rates"]![0]!["rate_usd"] = 999m; run.Files.Save();
            run.Transport.PostRelease.TrySetResult(true);
            timer.Restart(); while (run.Transport.Posts < 3 && timer.ElapsedMilliseconds < 5000) await Task.Delay(10);
            Assert.Equal(3, run.Transport.Posts);
            var record = System.Linq.Enumerable.Single(run.Images.ReadAll().Records, r => r.JobId == queued);
            Assert.Equal("canonical prompt", record.ConfiguredFalExecution!.Snapshot!.Request.EffectiveRequestFields["prompt"]!.GetValue<string>());
            Assert.Equal(.01m, record.ConfiguredFalExecution.Snapshot.Pricing!.EstimateMaxUsd);
        }
    }
}
