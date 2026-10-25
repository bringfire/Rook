$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../verify-fal-config-acceptance.ps1')
function Assert-Test([bool]$Condition, [string]$Message) { if (!$Condition) { throw $Message } }
Assert-Test (!(Test-FalJsonEqual ([double]::Epsilon) 0)) 'Numeric evidence underflow must not equal zero.'
Assert-Test (Test-FalJsonEqual ([decimal]0.123456) ([double]0.123456)) 'Equivalent admitted numeric values must compare equally.'
Assert-Test (!(Test-FalJsonEqual '0.123456' ([double]0.123456))) 'Numeric strings must not equal numbers.'
$hash = 'a' * 64
$freeze = [pscustomobject]@{ schema_version=1;policy='fal-runtime-freeze-v1';created_utc='2026-01-01T00:00:00Z';catalog_models=@();catalog_endpoints=@();roots=@([pscustomobject]@{name='code';path='C:/fixture';kind='source';files=@(@{path='compiler.cs';sha256=$hash;bytes=8})}) }
$proof = [pscustomobject]@{ schema_version=1;freeze_sha256=$hash;cases_sha256=$hash;reviewer='fixture reviewer';reviewed_utc='2026-01-02T00:00:00Z';spend_authorization=@{maintainer='fixture maintainer';approved_utc='2026-01-02T00:00:00Z';cap_usd=4};endpoints=@();live_jobs=@();qualification=@() }
$caseDataTests = [pscustomobject]@{ cases=@() }
foreach ($modality in @('image','video')) {
    $endpoint = [pscustomobject]@{model_id="synthetic/$modality";endpoint="fal-ai/synthetic/$modality";operation="text_to_$modality";modality=$modality;definition_hash=$hash;selected_utc='2026-01-03T00:00:00Z';documentation=@{url='https://fal.ai/models/synthetic';reviewed_on='2026-01-03';schema_sha256=$hash;pricing_sha256=$hash};controls=@(@{name='guidance';type='number'},@{name='audio';type='boolean'})}
    $proof.endpoints += $endpoint
    foreach ($surface in @('panel','mcp')) {
        $id="$modality-$surface"
        $caseDataTests.cases += [pscustomobject]@{id=$id;surface=$surface;request=@{model=$endpoint.model_id};expected=@{provider_payload=@{guidance=7.5;audio=$false}}}
        $proof.live_jobs += [pscustomobject]@{case_id=$id;job_id=[Guid]::NewGuid().ToString();artifact_id=[Guid]::NewGuid().ToString();model_id=$endpoint.model_id;endpoint=$endpoint.endpoint;operation=$endpoint.operation;definition_hash=$hash;runtime_sha256=$hash;surface=$surface;mode='live';state='completed';result_mime="$modality/example";normalized_sha256=$hash;payload_sha256=$hash;request_sha256=$hash;quote_fingerprint=('fal1:'+$hash);max_estimated_cost_usd=1;started_utc='2026-01-04T00:00:00Z';completed_utc='2026-01-04T00:00:01Z';actual_spend=@{status='unavailable'};selected_controls=[pscustomobject]@{guidance=7.5;audio=$false};capture=@{path='capture.json';sha256=$hash};provenance=@{path='provenance.json';sha256=$hash};artifact=@{path='result.bin';sha256=$hash}}
    }
}
foreach ($name in @('native_build','managed_builds','regression','package','installed_mcp','installed_panel','loaded_paths')) { $proof.qualification += @{name=$name;exit_code=0;path="$name.json";sha256=$hash} }
Assert-Test (@(Get-FalAcceptanceIssues $freeze $caseDataTests $proof $freeze $hash $hash).Count -eq 0) 'Complete joined evidence rejected.'
function Copy-Proof { $proof | ConvertTo-Json -Depth 30 | ConvertFrom-Json }
foreach ($count in 0..3) {
    $incomplete=Copy-Proof; $incomplete.live_jobs=@($proof.live_jobs | Select-Object -First $count)
    Assert-Test (@(Get-FalAcceptanceIssues $freeze $caseDataTests $incomplete $freeze $hash $hash).Count -gt 0) "Accepted only $count live jobs."
}
$changed=$freeze | ConvertTo-Json -Depth 20 | ConvertFrom-Json
$changed.roots[0].files += [pscustomobject]@{path='new.cs';sha256=$hash;bytes=9}
Assert-Test (@(Get-FalAcceptanceIssues $freeze $caseDataTests $proof $changed $hash $hash).Count -gt 0) 'Added code accepted.'
$changed.roots[0].files=@()
Assert-Test (@(Get-FalAcceptanceIssues $freeze $caseDataTests $proof $changed $hash $hash).Count -gt 0) 'Deleted code accepted.'
$invalid=Copy-Proof; $invalid.live_jobs[0].definition_hash='b'*64
Assert-Test (@(Get-FalAcceptanceIssues $freeze $caseDataTests $invalid $freeze $hash $hash).Count -gt 0) 'Mismatched definition accepted.'
$invalid=Copy-Proof; $invalid.live_jobs[0].mode='fixture'
Assert-Test (@(Get-FalAcceptanceIssues $freeze $caseDataTests $invalid $freeze $hash $hash).Count -gt 0) 'Fixture substituted for live job.'
$invalid=Copy-Proof; $invalid.qualification=@()
Assert-Test (@(Get-FalAcceptanceIssues $freeze $caseDataTests $invalid $freeze $hash $hash).Count -gt 0) 'Missing installed qualification accepted.'
$invalid=Copy-Proof; $invalid.endpoints[0].selected_utc='2025-01-01T00:00:00Z'
Assert-Test (@(Get-FalAcceptanceIssues $freeze $caseDataTests $invalid $freeze $hash $hash).Count -gt 0) 'Pre-freeze endpoint accepted.'
$temp=Join-Path ([IO.Path]::GetTempPath()) ('rook-acceptance-'+[Guid]::NewGuid().ToString('N')); New-Item -ItemType Directory -Path $temp | Out-Null
try {
    '{}' | Set-Content (Join-Path $temp 'empty.json')
    $exit=Invoke-FalConfigAcceptance (Join-Path $temp 'empty.json') (Join-Path $temp 'empty.json') (Join-Path $temp 'empty.json') (Join-Path $temp 'report.json')
    Assert-Test ($exit -ne 0) 'Empty fixture-only acceptance returned success.'
    $file=Join-Path $temp 'proof.json'; 'actual' | Set-Content $file
    $link=@{path='proof.json';sha256=(Get-FileHash $file).Hash}
    $null=Assert-FalEvidenceFile $link $temp
    'changed' | Set-Content $file
    $rejected=$false; try { $null=Assert-FalEvidenceFile $link $temp } catch { $rejected=$true }; Assert-Test $rejected 'Tampered evidence accepted.'
} finally {
    $resolved=[IO.Path]::GetFullPath($temp)
    Assert-Test ($resolved.StartsWith([IO.Path]::GetFullPath([IO.Path]::GetTempPath()),[StringComparison]::OrdinalIgnoreCase) -and [IO.Path]::GetFileName($resolved).StartsWith('rook-acceptance-')) 'Unsafe fixture cleanup.'
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
Write-Host 'PASS: fail-closed acceptance evidence, four live jobs, code inventory, hashes and installed gates.'

# Complete production-verifier traversal using a real temporary Git/file tree and
# actual qualifier output. These records are synthetic UNIT fixtures, not live proof.
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$qualifier = Join-Path $repo 'src/Rook.Vision.Qualification/bin/Release/net48/Rook.Vision.Qualification.exe'
if (!(Test-Path -LiteralPath $qualifier)) { $qualifier = Join-Path $repo 'src/Rook.Vision.Qualification/bin/Debug/net48/Rook.Vision.Qualification.exe' }
Assert-Test (Test-Path -LiteralPath $qualifier) 'Build the real qualifier before complete acceptance tests.'
$unitRoot = Join-Path ([IO.Path]::GetTempPath()) ('rook-acceptance-full-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $unitRoot | Out-Null
try {
    foreach ($path in @('src/Rook/Services/Vision/Fal/Models','scripts','mcp_server/src/rook','installer','plugin/net8.0','mcp/venv/Scripts','mcp/venv/Lib/site-packages/rook','outside/Lib/site-packages/rook','plugin-other','artifacts')) { New-Item -ItemType Directory -Path (Join-Path $unitRoot $path) -Force | Out-Null }
    '{"schema_version":1,"definitions":[]}' | Set-Content (Join-Path $unitRoot 'src/Rook/Services/Vision/Fal/Models/catalog.json')
    'compiler fixture' | Set-Content (Join-Path $unitRoot 'src/Rook/Services/Vision/Fal/Models/compiler.cs')
    'harness fixture' | Set-Content (Join-Path $unitRoot 'scripts/harness.ps1')
    'python fixture' | Set-Content (Join-Path $unitRoot 'mcp_server/src/rook/fixture.py')
    'installer fixture' | Set-Content (Join-Path $unitRoot 'installer/fixture.txt')
    'native fixture' | Set-Content (Join-Path $unitRoot 'plugin/RookNative.rhp')
    'managed fixture' | Set-Content (Join-Path $unitRoot 'plugin/net8.0/Rook.rhp')
    'python executable fixture' | Set-Content (Join-Path $unitRoot 'mcp/venv/Scripts/python.exe')
    'rook package fixture' | Set-Content (Join-Path $unitRoot 'mcp/venv/Lib/site-packages/rook/__init__.py')
    'outside python fixture' | Set-Content (Join-Path $unitRoot 'outside/python.exe')
    'outside package fixture' | Set-Content (Join-Path $unitRoot 'outside/Lib/site-packages/rook/__init__.py')
    'sibling plugin fixture' | Set-Content (Join-Path $unitRoot 'plugin-other/Rook.rhp')
    "artifacts/`nplugin/`nplugin-other/`nmcp/`noutside/`n**/bin/" | Set-Content (Join-Path $unitRoot '.gitignore')
    foreach ($tfm in @('net48','net7.0','net8.0')) {
        $built = Join-Path $unitRoot "src/Rook/bin/Release/$tfm"; New-Item -ItemType Directory -Path $built -Force | Out-Null; 'managed fixture' | Set-Content (Join-Path $built 'Rook.rhp')
        $hostDir = Join-Path $unitRoot "src/Rook.Vision.Qualification/bin/Release/$tfm"; New-Item -ItemType Directory -Path $hostDir -Force | Out-Null
        if ($tfm -eq 'net48') { Copy-Item -Path ((Split-Path $qualifier) + '/*') -Destination $hostDir -Recurse } else { 'target fixture' | Set-Content (Join-Path $hostDir 'host.dll') }
    }
    $native = Join-Path $unitRoot 'src/RookNative/bin/Release/x64'; New-Item -ItemType Directory -Path $native -Force | Out-Null; 'native fixture' | Set-Content (Join-Path $native 'RookNative.rhp')
    & git -C $unitRoot init --quiet
    & git -C $unitRoot add .
    & git -C $unitRoot -c user.name=UnitFixture -c user.email=unit@example.invalid commit -m 'unit fixture' --quiet
    Assert-Test ($LASTEXITCODE -eq 0) 'Could not commit temporary fixture.'
    $unitExe = Join-Path $unitRoot 'src/Rook.Vision.Qualification/bin/Release/net48/Rook.Vision.Qualification.exe'
    $attempt = Join-Path $unitRoot 'artifacts/attempt'; New-Item -ItemType Directory -Path $attempt | Out-Null
    $freezePath = Join-Path $attempt 'freeze.json'
    & $unitExe freeze-runtime --repo $unitRoot --plugin-root (Join-Path $unitRoot 'plugin') --mcp-root (Join-Path $unitRoot 'mcp') --out $freezePath
    Assert-Test ($LASTEXITCODE -eq 0) 'Real freeze-runtime failed for temporary fixture.'
    $fullFreeze=Get-Content $freezePath -Raw | ConvertFrom-Json
    $fixtures=Join-Path $repo 'src/Rook.Tests/Services/Vision/Fal/Fixtures'; $fullCases=Join-Path $fixtures 'configured-cases.json'
    # Original frozen capture programs remain available under the original checkout.
    & $qualifier verify-cases --catalog $fixtures --cases $fullCases --report (Join-Path $attempt 'conformance.json')
    Assert-Test ($LASTEXITCODE -eq 0) 'Actual generic conformance failed in verifier unit test.'
    $conformance=Get-Content (Join-Path $attempt 'conformance.json') -Raw | ConvertFrom-Json
    function Unit-Link([string]$Name) { @{path=$Name;sha256=(Get-FileHash -LiteralPath (Join-Path $attempt $Name)).Hash.ToLowerInvariant()} }
    $fullProof=Copy-Proof
    $fullProof.freeze_sha256=(Get-FileHash $freezePath).Hash.ToLowerInvariant(); $fullProof.cases_sha256=(Get-FileHash $fullCases).Hash.ToLowerInvariant()
    $reviewTime=([DateTimeOffset]$fullFreeze.created_utc).AddSeconds(1).ToString('O')
    $selectionTime=([DateTimeOffset]$fullFreeze.created_utc).AddSeconds(2).ToString('O')
    $time=([DateTimeOffset]$fullFreeze.created_utc).AddSeconds(3).ToString('O')
    $fullProof.reviewed_utc=$reviewTime; $fullProof.spend_authorization.approved_utc=$reviewTime; $fullProof.spend_authorization.cap_usd=10
    $fullProof.endpoints=@(); $fullProof.live_jobs=@(); $fullProof.qualification=@()
    $fullProof | Add-Member -NotePropertyName conformance -NotePropertyValue (Unit-Link 'conformance.json')
    foreach ($modality in @('image','video')) {
        $prefix=if ($modality -eq 'image') {'sync-image'} else {'queue-video'}
        $reference=@($conformance.cases | Where-Object id -eq "$prefix-panel-controls")[0]
        $endpoint=[pscustomobject]@{model_id=$reference.model_id;endpoint=$reference.endpoint;operation=$reference.operation;modality=$modality;definition_hash=$reference.definition_hash;selected_utc=$selectionTime;documentation=@{url='https://fal.ai/models/synthetic';reviewed_on='2026-01-01';schema_sha256=$hash;pricing_sha256=$hash};controls=@(@{name='strength';type='number'},@{name='audio';type='boolean'})}
        $fullProof.endpoints += $endpoint
        foreach ($surface in @('panel','mcp')) {
            $row=@($conformance.cases | Where-Object id -eq "$prefix-$surface-controls")[0]; $jobId=[Guid]::NewGuid().ToString();$artifactId=[Guid]::NewGuid().ToString();$id="$modality-$surface"
            @{surface=$surface;request_sha256=$row.request_sha256;normalized_sha256=$row.normalized_sha256;payload_sha256=$row.payload_sha256;confirmation=@{quote_fingerprint=$row.quote_fingerprint;max_estimated_cost_usd=$row.cap_usd};quote=$row.quote} | ConvertTo-Json -Depth 30 | Set-Content (Join-Path $attempt "$id-capture.json")
            @{job_id=$jobId;artifact_id=$artifactId;definition_hash=$row.definition_hash;effective_request=$row.effective_request;effective_options=$row.effective_options;pricing=$row.provenance.pricing;media=$row.media} | ConvertTo-Json -Depth 30 | Set-Content (Join-Path $attempt "$id-provenance.json")
            'synthetic artifact UNIT DATA, not a live generation' | Set-Content (Join-Path $attempt "$id-artifact.bin")
            $fullProof.live_jobs += [pscustomobject]@{case_id=$row.id;job_id=$jobId;artifact_id=$artifactId;model_id=$row.model_id;endpoint=$row.endpoint;operation=$row.operation;definition_hash=$row.definition_hash;runtime_sha256=$fullProof.freeze_sha256;surface=$surface;mode='live';state='completed';result_mime="$modality/example";request_sha256=$row.request_sha256;normalized_sha256=$row.normalized_sha256;payload_sha256=$row.payload_sha256;quote_fingerprint=$row.quote_fingerprint;max_estimated_cost_usd=$row.cap_usd;started_utc=$time;completed_utc=$time;selected_controls=$row.effective_options;actual_spend=@{status='unavailable'};capture=(Unit-Link "$id-capture.json");provenance=(Unit-Link "$id-provenance.json");artifact=(Unit-Link "$id-artifact.bin")}
        }
    }
    foreach ($name in @('native_build','managed_builds','regression','package','installed_mcp','installed_panel')) {
        @{unit_fixture=$true;command='synthetic qualification fixture';exit_code=0} | ConvertTo-Json | Set-Content (Join-Path $attempt "$name.json")
        $link=Unit-Link "$name.json"; $link.name=$name;$link.exit_code=0;$fullProof.qualification += $link
    }
    $modules=@();foreach ($path in @('plugin/RookNative.rhp','plugin/net8.0/Rook.rhp')) { $file=Join-Path $unitRoot $path; $modules+=@{name=[IO.Path]::GetFileName($file);path=$file;version='unit-fixture';sha256=(Get-FileHash $file).Hash} }
    @{process_id=1;process_started_utc=$time;observed_utc=$time;modules=$modules;python=@{path=(Join-Path $unitRoot 'mcp/venv/Scripts/python.exe');package_path=(Join-Path $unitRoot 'mcp/venv/Lib/site-packages/rook/__init__.py');sha256=(Get-FileHash (Join-Path $unitRoot 'mcp/venv/Scripts/python.exe')).Hash;package_sha256=(Get-FileHash (Join-Path $unitRoot 'mcp/venv/Lib/site-packages/rook/__init__.py')).Hash}} | ConvertTo-Json -Depth 20 | Set-Content (Join-Path $attempt 'loaded.json')
    $link=Unit-Link 'loaded.json';$link.name='loaded_paths';$link.exit_code=0;$fullProof.qualification += $link
    $evidencePath=Join-Path $attempt 'evidence.json';$reportPath=Join-Path $attempt 'acceptance.json'
    $fullProof | ConvertTo-Json -Depth 50 | Set-Content $evidencePath
    Assert-Test ((Invoke-FalConfigAcceptance $freezePath $fullCases $evidencePath $reportPath) -eq 0) 'Complete production verifier positive UNIT path failed.'
    $baselineProof=$fullProof | ConvertTo-Json -Depth 50
    $captureName=$fullProof.live_jobs[0].capture.path; $provenanceName=$fullProof.live_jobs[0].provenance.path
    $baselineCapture=Get-Content (Join-Path $attempt $captureName) -Raw
    $baselineProvenance=Get-Content (Join-Path $attempt $provenanceName) -Raw
    $baselineLoaded=Get-Content (Join-Path $attempt 'loaded.json') -Raw
    $acceptedTampering=[Collections.Generic.List[string]]::new()
    function Assert-UnitTamperRejected([string]$Name,[scriptblock]$Tamper) {
        $candidate=$baselineProof | ConvertFrom-Json; $captured=$baselineCapture | ConvertFrom-Json
        $saved=$baselineProvenance | ConvertFrom-Json; $loadedFixture=$baselineLoaded | ConvertFrom-Json
        & $Tamper $candidate $captured $saved $loadedFixture
        $captured | ConvertTo-Json -Depth 40 | Set-Content (Join-Path $attempt $captureName)
        $saved | ConvertTo-Json -Depth 40 | Set-Content (Join-Path $attempt $provenanceName)
        $loadedFixture | ConvertTo-Json -Depth 40 | Set-Content (Join-Path $attempt 'loaded.json')
        $candidate.live_jobs[0].capture.sha256=(Unit-Link $captureName).sha256
        $candidate.live_jobs[0].provenance.sha256=(Unit-Link $provenanceName).sha256
        @($candidate.qualification | Where-Object name -eq 'loaded_paths')[0].sha256=(Unit-Link 'loaded.json').sha256
        $candidate | ConvertTo-Json -Depth 50 | Set-Content $evidencePath
        if ((Invoke-FalConfigAcceptance $freezePath $fullCases $evidencePath $reportPath) -eq 0) { $acceptedTampering.Add($Name) }
        else { Write-Host "PASS tamper rejected: $Name" }
    }
    Assert-UnitTamperRejected 'selected numeric value' { param($p,$c,$s,$l) $p.live_jobs[0].selected_controls.strength=999 }
    Assert-UnitTamperRejected 'selected numeric type' { param($p,$c,$s,$l) $p.live_jobs[0].selected_controls.strength='0.123456' }
    Assert-UnitTamperRejected 'selected boolean type' { param($p,$c,$s,$l) $p.live_jobs[0].selected_controls.audio='not-a-boolean' }
    Assert-UnitTamperRejected 'confirmed cap undercount' { param($p,$c,$s,$l) $p.live_jobs[0].max_estimated_cost_usd=0 }
    Assert-UnitTamperRejected 'boolean cost cap' { param($p,$c,$s,$l) $p.live_jobs[0].max_estimated_cost_usd=$false }
    Assert-UnitTamperRejected 'job quote fingerprint' { param($p,$c,$s,$l) $p.live_jobs[0].quote_fingerprint='fal1:'+('b'*64) }
    Assert-UnitTamperRejected 'consistent capture and job wrong request' { param($p,$c,$s,$l) $p.live_jobs[0].request_sha256='b'*64; $c.request_sha256='b'*64 }
    Assert-UnitTamperRejected 'captured confirmation cap' { param($p,$c,$s,$l) $c.confirmation.max_estimated_cost_usd=0 }
    Assert-UnitTamperRejected 'captured confirmation fingerprint' { param($p,$c,$s,$l) $c.confirmation.quote_fingerprint='fal1:'+('b'*64) }
    Assert-UnitTamperRejected 'captured quoted bound' { param($p,$c,$s,$l) $c.quote.max_estimated_cost_usd=0 }
    Assert-UnitTamperRejected 'captured pricing' { param($p,$c,$s,$l) $c.quote.pricing.rate_usd=999 }
    Assert-UnitTamperRejected 'saved controls' { param($p,$c,$s,$l) $s.effective_options.strength=999 }
    Assert-UnitTamperRejected 'saved common request' { param($p,$c,$s,$l) $s.effective_request.seed=123 }
    Assert-UnitTamperRejected 'saved pricing' { param($p,$c,$s,$l) $s.pricing.rate_usd=999 }
    Assert-UnitTamperRejected 'saved media' { param($p,$c,$s,$l) $s.media=@(@{role='reference';sha256=('b'*64)}) }
    Assert-UnitTamperRejected 'missing saved pricing' { param($p,$c,$s,$l) $s.PSObject.Properties.Remove('pricing') }
    Assert-UnitTamperRejected 'outside interpreter' { param($p,$c,$s,$l) $l.python.path=Join-Path $unitRoot 'outside/python.exe'; $l.python.sha256=(Get-FileHash $l.python.path).Hash }
    Assert-UnitTamperRejected 'nonexistent package' { param($p,$c,$s,$l) $l.python.package_path=Join-Path $unitRoot 'mcp/venv/Lib/site-packages/missing/__init__.py' }
    Assert-UnitTamperRejected 'outside package' { param($p,$c,$s,$l) $l.python.package_path=Join-Path $unitRoot 'outside/Lib/site-packages/rook/__init__.py'; $l.python.package_sha256=(Get-FileHash $l.python.package_path).Hash }
    Assert-UnitTamperRejected 'package digest' { param($p,$c,$s,$l) $l.python.package_sha256='b'*64 }
    Assert-UnitTamperRejected 'plugin prefix sibling' { param($p,$c,$s,$l) $module=@($l.modules | Where-Object name -eq 'Rook.rhp')[0]; $module.path=Join-Path $unitRoot 'plugin-other/Rook.rhp'; $module.sha256=(Get-FileHash $module.path).Hash }
    Assert-UnitTamperRejected 'selection before reviewer signoff' { param($p,$c,$s,$l) $p.endpoints[0].selected_utc=([DateTimeOffset]$fullFreeze.created_utc).AddMilliseconds(500).ToString('O') }
    Assert-UnitTamperRejected 'jobs before selection' { param($p,$c,$s,$l) $p.live_jobs[0].started_utc=$reviewTime }
    $baselineCapture | Set-Content (Join-Path $attempt $captureName); $baselineProvenance | Set-Content (Join-Path $attempt $provenanceName); $baselineLoaded | Set-Content (Join-Path $attempt 'loaded.json')
    # Refresh links because Set-Content may change trailing newlines in restored fixture files.
    $fullProof.live_jobs[0].capture.sha256=(Unit-Link $captureName).sha256; $fullProof.live_jobs[0].provenance.sha256=(Unit-Link $provenanceName).sha256
    @($fullProof.qualification | Where-Object name -eq 'loaded_paths')[0].sha256=(Unit-Link 'loaded.json').sha256
    Assert-Test ($acceptedTampering.Count -eq 0) ('Complete verifier accepted tampering: '+($acceptedTampering -join ', '))
    $fullProof.live_jobs[0].normalized_sha256='b'*64
    $fullProof | ConvertTo-Json -Depth 50 | Set-Content $evidencePath
    Assert-Test ((Invoke-FalConfigAcceptance $freezePath $fullCases $evidencePath $reportPath) -ne 0) 'Complete verifier accepted mismatched normalized row.'
    $fullProof.live_jobs=@($fullProof.live_jobs | Select-Object -Skip 1)
    $fullProof | ConvertTo-Json -Depth 50 | Set-Content $evidencePath
    Assert-Test ((Invoke-FalConfigAcceptance $freezePath $fullCases $evidencePath $reportPath) -ne 0) 'Complete verifier accepted missing live row.'
    Write-Host 'PASS: complete production verifier positive/negative paths on synthetic UNIT files; no live acceptance claimed.'
} finally {
    $resolved=[IO.Path]::GetFullPath($unitRoot)
    Assert-Test ($resolved.StartsWith([IO.Path]::GetFullPath([IO.Path]::GetTempPath()),[StringComparison]::OrdinalIgnoreCase) -and [IO.Path]::GetFileName($resolved).StartsWith('rook-acceptance-full-')) 'Unsafe complete-fixture cleanup.'
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
