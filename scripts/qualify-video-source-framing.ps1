[CmdletBinding()]
param([string]$ReportRoot = 'artifacts/video-source-framing-qualification')
$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$report = [IO.Path]::GetFullPath((Join-Path $repo $ReportRoot))
$artifactRoot = [IO.Path]::GetFullPath((Join-Path $repo 'artifacts')) + [IO.Path]::DirectorySeparatorChar
if (!$report.StartsWith($artifactRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Qualification reports/stages must stay inside this checkout artifacts directory.' }
$run = Join-Path $report ([DateTime]::UtcNow.ToString('yyyyMMddTHHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8))
New-Item -ItemType Directory -Path $run -Force | Out-Null
Push-Location $repo
try {
    # This property explicitly disables the companion's normal Release deployment target.
    & dotnet build src/Rook.Framing.Qualification/Rook.Framing.Qualification.csproj -c Release '-p:RhinoPluginDir=' *> (Join-Path $run 'build.log')
    if ($LASTEXITCODE) { throw "Qualification build failed; see $run/build.log" }
    $fixtures = Join-Path $repo 'third_party/ffmpeg/fixtures/framing'
    if (!(Test-Path (Join-Path $repo 'artifacts/video-framing-fixtures/generated-noise-4k.png'))) {
        throw 'Generate the deterministic stress fixture using generate-fixtures.py --include-noise first (existing Pillow developer tooling).'
    }
    $records = @()
    $reference = $null
    foreach ($framework in @('net48','net7.0','net8.0')) {
        $stage = Join-Path $run "stage-$framework"
        New-Item -ItemType Directory -Path $stage | Out-Null
        Copy-Item -Path (Join-Path $repo "src/Rook.Framing.Qualification/bin/Release/$framework/*") -Destination $stage -Recurse -Force
        $ffmpeg = Join-Path $stage 'ffmpeg'
        New-Item -ItemType Directory -Path $ffmpeg -Force | Out-Null
        foreach ($file in @('ffmpeg.exe','ffmpeg-provenance.json','LICENSE.FFmpeg.txt','LICENSE.zlib.txt','NOTICE.FFmpeg.txt','SOURCE.FFmpeg.txt')) {
            Copy-Item -LiteralPath (Join-Path $repo "third_party/ffmpeg/$file") -Destination $ffmpeg -Force
        }
        $exe = Join-Path $stage 'Rook.Framing.Qualification.exe'
        $renderReport = Join-Path $run "renderer-$framework.json"
        & $exe --installed-layout --fixtures $fixtures --report $renderReport *> (Join-Path $run "renderer-$framework.log")
        if ($LASTEXITCODE) { throw "Renderer qualification failed for $framework; see $run/renderer-$framework.log" }
        $processReport = Join-Path $run "process-$framework.json"
        & $exe --process-probes --report $processReport *> (Join-Path $run "process-$framework.log")
        if ($LASTEXITCODE) { throw "Process qualification failed for $framework; see $run/process-$framework.log" }
        $render = Get-Content -LiteralPath $renderReport -Raw | ConvertFrom-Json
        if ([IO.Path]::GetFullPath($render.binary) -ne [IO.Path]::GetFullPath((Join-Path $ffmpeg 'ffmpeg.exe'))) { throw 'Production locator escaped staged adjacent payload.' }
        $identity = $render.records | Sort-Object key | ForEach-Object { "$($_.key)|$($_.prepared)|$($_.recipe | ConvertTo-Json -Depth 20 -Compress)" }
        $canonical = $identity -join "`n"
        if ($null -ne $reference -and $reference -cne $canonical) { throw "Target-dependent output or recipe in $framework" }
        $reference = $canonical
        $records += [ordered]@{
            framework = $framework
            rendering_cases = $render.records.Count
            legacy_decode_cases = $render.legacy_validation.Count
            assembly_sha256 = (Get-FileHash -LiteralPath (Join-Path $stage 'Rook.dll') -Algorithm SHA256).Hash
            renderer_sha256 = (Get-FileHash -LiteralPath (Join-Path $ffmpeg 'ffmpeg.exe') -Algorithm SHA256).Hash
            manifest_sha256 = (Get-FileHash -LiteralPath (Join-Path $fixtures 'manifest.json') -Algorithm SHA256).Hash
            renderer_report = $renderReport
            process_report = $processReport
        }
        if ($render.legacy_validation.Count -ne 10) { throw 'Legacy compressed-pixel validation cases are missing.' }
        Write-Host "PASS $framework : $($render.records.Count) rendering cases, $($render.legacy_validation.Count) legacy decode cases and Windows containment probes"
    }
    [ordered]@{ run = $run; utc = [DateTime]::UtcNow.ToString('O'); staged_only = $true; targets = $records } |
        ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $run 'qualification.json') -Encoding utf8
    Write-Host "PASS staged qualification: $run"
} finally { Pop-Location }
