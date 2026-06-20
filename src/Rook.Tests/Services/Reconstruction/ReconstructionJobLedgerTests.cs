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
