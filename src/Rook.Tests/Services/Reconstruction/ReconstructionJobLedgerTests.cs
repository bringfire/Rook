using System;
using System.IO;
using Rook.Services.Reconstruction;
using Xunit;

namespace Rook.Tests.Services.Reconstruction;

public sealed class ReconstructionJobLedgerTests
{
    [Fact]
    public void AppendAndList_PreservesResultAvailabilityAndWarnings()
    {
        var path = Path.Combine(
            Path.GetTempPath(),
            $"rook-reconstruction-ledger-{Guid.NewGuid():N}.jsonl");
        var ledger = new JsonlReconstructionJobLedger(path);
        var jobId = Guid.NewGuid();
        var artifactId = Guid.NewGuid();

        ledger.Append(ReconstructionJobLedgerRecord.Queued(
            jobId,
            "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d",
            Guid.NewGuid(),
            "image"));
        ledger.Append(ReconstructionJobLedgerRecord.Complete(jobId, artifactId));

        var jobs = ledger.List(limit: 100);

        var only = Assert.Single(jobs.Jobs);
        Assert.Equal(jobId, only.JobId);
        Assert.Equal(ReconstructionJobState.Complete, only.State);
        Assert.Equal(ReconstructionJobStage.Complete, only.Stage);
        Assert.Equal(artifactId, only.ResultArtifactId);
        Assert.True(only.ResultAvailable);
        Assert.Empty(jobs.Warnings);
    }

    [Fact]
    public void Append_Then_List_RoundTrips_TextureExpected_True()
    {
        var path = Path.Combine(Path.GetTempPath(), $"rook-ledger-{Guid.NewGuid():N}.jsonl");
        try
        {
            var ledger = new JsonlReconstructionJobLedger(path);
            var rec = ReconstructionJobLedgerRecord.Queued(
                Guid.NewGuid(), "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d", Guid.NewGuid(), "image",
                textureExpected: true);
            ledger.Append(rec);

            var read = Assert.Single(ledger.List(10).Jobs);
            Assert.True(read.TextureExpected);
        }
        finally { if (File.Exists(path)) File.Delete(path); }
    }

    [Fact]
    public void List_ReadsLegacyV1Record_WithTextureExpectedFalse_NotDropped()
    {
        var path = Path.Combine(Path.GetTempPath(), $"rook-ledger-{Guid.NewGuid():N}.jsonl");
        try
        {
            // A hand-written v1 line: schema_version 1, NO texture_expected key.
            var jobId = Guid.NewGuid();
            var v1 = $$"""
            {"schema_version":1,"job_id":"{{jobId:D}}","state":"Complete","stage":"Complete","provider":"fal","model_id":"fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d","source_artifact_id":"{{Guid.NewGuid():D}}","source_role":"image","created_at":"2026-06-20T00:00:00.0000000+00:00","updated_at":"2026-06-20T00:00:00.0000000+00:00","result_available":false,"preprocessing_chain":[]}
            """;
            File.WriteAllText(path, v1 + "\n");

            var ledger = new JsonlReconstructionJobLedger(path);
            var result = ledger.List(10);

            var job = Assert.Single(result.Jobs);                  // NOT dropped as unsupported
            Assert.Equal(jobId, job.JobId);
            Assert.False(job.TextureExpected);                      // absent → false
            Assert.DoesNotContain(result.Warnings, w => w.Code == "unsupported_schema_version");
        }
        finally { if (File.Exists(path)) File.Delete(path); }
    }

    [Fact]
    public void List_RejectsFutureSchemaVersion_AsUnsupported()
    {
        var path = Path.Combine(Path.GetTempPath(), $"rook-ledger-{Guid.NewGuid():N}.jsonl");
        try
        {
            var future = $$"""
            {"schema_version":99,"job_id":"{{Guid.NewGuid():D}}","state":"Complete","stage":"Complete","provider":"fal","model_id":"x","source_role":"image","result_available":false,"preprocessing_chain":[]}
            """;
            File.WriteAllText(path, future + "\n");

            var result = new JsonlReconstructionJobLedger(path).List(10);

            Assert.Empty(result.Jobs);
            Assert.Contains(result.Warnings, w => w.Code == "unsupported_schema_version");
        }
        finally { if (File.Exists(path)) File.Delete(path); }
    }

    [Fact]
    public void List_SkipsMalformedLines_AndPreservesWarning()
    {
        var path = Path.Combine(
            Path.GetTempPath(),
            $"rook-reconstruction-ledger-{Guid.NewGuid():N}.jsonl");
        var ledger = new JsonlReconstructionJobLedger(path);
        var jobId = Guid.NewGuid();
        ledger.Append(ReconstructionJobLedgerRecord.Queued(
            jobId,
            "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d",
            Guid.NewGuid(),
            "image"));
        File.AppendAllText(path, "{not json" + Environment.NewLine);

        var jobs = ledger.List(limit: 100);

        Assert.Single(jobs.Jobs);
        var warning = Assert.Single(jobs.Warnings);
        Assert.Equal("malformed_json", warning.Code);
    }

    [Fact]
    public void List_AppliesLimitNewestFirst()
    {
        var path = Path.Combine(
            Path.GetTempPath(),
            $"rook-reconstruction-ledger-{Guid.NewGuid():N}.jsonl");
        var ledger = new JsonlReconstructionJobLedger(path);

        ledger.Append(ReconstructionJobLedgerRecord.Queued(
            Guid.NewGuid(),
            "old",
            Guid.NewGuid(),
            "image"));
        var newest = Guid.NewGuid();
        ledger.Append(ReconstructionJobLedgerRecord.Queued(
            newest,
            "new",
            Guid.NewGuid(),
            "image"));

        var jobs = ledger.List(limit: 1);

        var only = Assert.Single(jobs.Jobs);
        Assert.Equal(newest, only.JobId);
        Assert.Equal(1, jobs.AppliedLimit);
    }
}
