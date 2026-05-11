param(
    [string]$InputMp4,
    [string]$FfmpegPath
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$findingsPath = Join-Path $repoRoot "docs\rook_docs\video-extraction-spike-findings.md"
$outputDir = Join-Path $repoRoot ".scratch\video-extraction-spike"

function Find-LatestRookVideo {
    $artifactRoot = Join-Path $env:APPDATA "Rook\artifacts"
    if (-not (Test-Path $artifactRoot)) {
        return $null
    }

    Get-ChildItem -Path $artifactRoot -Recurse -Filter "video.mp4" -File |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1 |
        ForEach-Object { $_.FullName }
}

$resolvedInput = $InputMp4
if ([string]::IsNullOrWhiteSpace($resolvedInput)) {
    $resolvedInput = $env:ROOK_VIDEO_SPIKE_MP4
}
if ([string]::IsNullOrWhiteSpace($resolvedInput)) {
    $resolvedInput = Find-LatestRookVideo
}

if ([string]::IsNullOrWhiteSpace($resolvedInput) -or -not (Test-Path $resolvedInput)) {
    throw "No local MP4 found. Pass -InputMp4, set ROOK_VIDEO_SPIKE_MP4, or generate a RookVision video artifact first."
}

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

$env:ROOK_RUN_VIDEO_EXTRACTION_SPIKE = "1"
$env:ROOK_VIDEO_SPIKE_MP4 = (Resolve-Path $resolvedInput).Path
$env:ROOK_VIDEO_SPIKE_FINDINGS_PATH = $findingsPath
$env:ROOK_VIDEO_SPIKE_OUTPUT_DIR = $outputDir
if (-not [string]::IsNullOrWhiteSpace($FfmpegPath)) {
    $env:ROOK_VIDEO_SPIKE_FFMPEG = (Resolve-Path $FfmpegPath).Path
} else {
    Remove-Item Env:\ROOK_VIDEO_SPIKE_FFMPEG -ErrorAction SilentlyContinue
}

Write-Host "Input MP4: $($env:ROOK_VIDEO_SPIKE_MP4)"
Write-Host "Findings:  $findingsPath"
Write-Host "Output:    $outputDir"

dotnet test "$repoRoot\src\Rook.Tests\Rook.Tests.csproj" --no-restore --filter "FullyQualifiedName~VideoExtractionSpikeManualTests"
if ($LASTEXITCODE -ne 0) {
    throw "Video extraction spike failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path $findingsPath)) {
    throw "Expected findings document was not written: $findingsPath"
}

Write-Host "Spike findings written to $findingsPath"
