Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$TestRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $TestRoot)
$VerifierPath = Join-Path $RepoRoot 'scripts\verify-containment-safe-rollback.ps1'
$WindowsPowerShell = 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
$script:TestsPassed = 0

if (-not (Test-Path -LiteralPath $VerifierPath -PathType Leaf)) {
    throw 'EXPECTED_RED:T10:ROLLBACK_MISSING'
}

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Assert-False {
    param([bool]$Condition, [string]$Message)
    if ($Condition) { throw $Message }
}

function Assert-Equal {
    param([AllowNull()][object]$Actual, [AllowNull()][object]$Expected, [string]$Message)
    if ($null -eq $Actual -and $null -eq $Expected) { return }
    if ($null -eq $Actual -or $null -eq $Expected -or [string]$Actual -cne [string]$Expected) {
        throw "$Message Expected=[$Expected] Actual=[$Actual]"
    }
}

function Assert-Contains {
    param([string]$Text, [string]$Needle, [string]$Message)
    Assert-True $Text.Contains($Needle) "$Message Missing=[$Needle]"
}

function Assert-ThrowsLike {
    param([scriptblock]$Body, [string]$Pattern, [string]$Message)
    $threw = $false
    try { & $Body } catch {
        $threw = $true
        if ([string]$_.Exception.Message -notmatch $Pattern) { throw "$Message Wrong error: $($_.Exception.Message)" }
    }
    if (-not $threw) { throw "$Message Expected failure matching [$Pattern]." }
}

function Write-TestUtf8NoBom {
    param([string]$Path, [string]$Text)
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path -LiteralPath $parent -PathType Container)) { [IO.Directory]::CreateDirectory($parent) | Out-Null }
    [IO.File]::WriteAllText($Path,$Text,[Text.UTF8Encoding]::new($false))
}

function Write-TestAscii {
    param([string]$Path, [string]$Text)
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path -LiteralPath $parent -PathType Container)) { [IO.Directory]::CreateDirectory($parent) | Out-Null }
    [IO.File]::WriteAllText($Path,$Text,[Text.Encoding]::ASCII)
}

function Get-TestSha256 {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function ConvertTo-TestCanonicalJson {
    param([AllowNull()][object]$Value)
    if ($null -eq $Value) { return 'null' }
    if ($Value -is [bool]) { if ($Value) { return 'true' } else { return 'false' } }
    if ($Value -is [string] -or $Value -is [char]) { return ConvertTo-Json -InputObject ([string]$Value) -Compress }
    if ($Value -is [byte] -or $Value -is [sbyte] -or $Value -is [int16] -or $Value -is [uint16] -or $Value -is [int32] -or $Value -is [uint32] -or $Value -is [int64] -or $Value -is [uint64] -or $Value -is [single] -or $Value -is [double] -or $Value -is [decimal]) {
        return [Convert]::ToString($Value,[Globalization.CultureInfo]::InvariantCulture)
    }
    if ($Value -is [Collections.IDictionary]) {
        [string[]]$keys = @($Value.Keys | ForEach-Object { [string]$_ })
        [Array]::Sort($keys,[StringComparer]::Ordinal)
        $parts = foreach($key in $keys){(ConvertTo-Json -InputObject $key -Compress)+':'+(ConvertTo-TestCanonicalJson -Value ($Value[$key]))}
        return '{'+($parts -join ',')+'}'
    }
    if ($Value -is [pscustomobject]) {
        $map=[ordered]@{}
        foreach($property in $Value.PSObject.Properties){$map[$property.Name]=$property.Value}
        return ConvertTo-TestCanonicalJson $map
    }
    if ($Value -is [Collections.IEnumerable]) {
        $items=foreach($item in $Value){ConvertTo-TestCanonicalJson $item}
        return '['+($items -join ',')+']'
    }
    throw "unsupported test JSON value: $($Value.GetType().FullName)"
}

function Get-TestTreeIdentity {
    param([string]$Root)
    $records = foreach($file in @(Get-ChildItem -LiteralPath $Root -Recurse -File | Sort-Object FullName)){
        [ordered]@{relative_path=$file.FullName.Substring($Root.TrimEnd('\').Length).TrimStart('\').Replace('\','/');size=[long]$file.Length;sha256=(Get-TestSha256 $file.FullName);write_ticks=$file.LastWriteTimeUtc.Ticks}
    }
    return ConvertTo-TestCanonicalJson @($records)
}

function Remove-TestTree {
    param([string]$Path)
    if(-not(Test-Path -LiteralPath $Path)){return}
    $full=[IO.Path]::GetFullPath($Path)
    $temp=[IO.Path]::GetFullPath($env:TEMP).TrimEnd('\')+'\'
    if(-not $full.StartsWith($temp,[StringComparison]::OrdinalIgnoreCase)){throw "refusing non-temp cleanup: $full"}
    Remove-Item -LiteralPath $full -Recurse -Force
}

function New-RollbackFixture {
    param([string]$Root)
    $fixture=Join-Path $Root ([guid]::NewGuid().ToString('N'))
    [IO.Directory]::CreateDirectory($fixture)|Out-Null
    $installer=Join-Path $fixture 'Rook-Setup.exe'
    Write-TestAscii $installer 'immutable-installer'
    $identity=[ordered]@{
        schema_version=1;non_publishable=$true;sources=[ordered]@{rook=[ordered]@{sha=('1'*40)};chirp=[ordered]@{sha=('2'*40)}}
        installer=[ordered]@{relative_path='Rook-Setup.exe';sha256=(Get-TestSha256 $installer)}
    }
    $identityPath=Join-Path $fixture 'containment-candidate.json'
    Write-TestUtf8NoBom $identityPath (ConvertTo-TestCanonicalJson $identity)
    $identityHash=Get-TestSha256 $identityPath
    $identitySidecar=Join-Path $fixture 'containment-candidate.sha256'
    Write-TestAscii $identitySidecar "$identityHash  containment-candidate.json`n"
    $diagnostic=Join-Path $fixture 'retained-diagnostic.json'
    Write-TestUtf8NoBom $diagnostic '{"retained":true}'
    $acceptance=[ordered]@{
        schema_version=1;success=$true;started_utc='2026-07-17T00:00:00.000000Z';ended_utc='2026-07-17T00:00:01.000000Z'
        validator=[ordered]@{sha256=('3'*64)}
        validator_result=[ordered]@{status='passed';success=$true}
        candidate=[ordered]@{
            identity_path=$identityPath;identity_sha256=$identityHash;sidecar_path=$identitySidecar;sidecar_sha256=(Get-TestSha256 $identitySidecar)
            installer_path=$installer;installer_sha256=(Get-TestSha256 $installer);rook_sha=('1'*40);chirp_sha=('2'*40)
        }
        installed_runtime=[ordered]@{python_executable='C:\Rook\venv\Scripts\python.exe';python_sha256=('4'*64);install_root='C:\Rook\app';processes=@()}
        quiescence=[ordered]@{preflight_quiet=$true;final_quiet=$true;records=@()}
        startup_isolation=[ordered]@{control_fired=$true;installed_sanitized=$true;installer_sanitized=$true;external_hits_absent=$true;PYTHONUSERBASE_absent=$true;PYTHONNOUSERSITE='1';probe_hashes=@()}
        discovery=[ordered]@{default=422;full=422;lean=20;readonly=148;interactive_full=425;contained_names_absent=$true}
        transport=[ordered]@{count=36;records=(0..35|ForEach-Object{[ordered]@{index=$_;valid=$true}})}
        internal=[ordered]@{count=164;records=(0..163|ForEach-Object{[ordered]@{index=$_;valid=$true}})}
        scenarios=[ordered]@{rhino=[ordered]@{success=$true;restoration_verified=$true;telemetry_delta=0};grasshopper=[ordered]@{success=$true;restoration_verified=$true;telemetry_delta=0}}
        diagnostics=@([ordered]@{relative_path='retained-diagnostic.json';sha256=(Get-TestSha256 $diagnostic);size=(Get-Item $diagnostic).Length})
        post_run_artifact_snapshot=[ordered]@{verified=$true;sha256=('5'*64)}
        restoration_verified=$true
        containment_hold=[ordered]@{activated=$false;receipt_path=$null;receipt_sha256=$null}
    }
    $acceptancePath=Join-Path $fixture 'containment-acceptance.json'
    Write-TestUtf8NoBom $acceptancePath (ConvertTo-TestCanonicalJson $acceptance)
    $acceptanceHash=Get-TestSha256 $acceptancePath
    $acceptanceSidecar=Join-Path $fixture 'containment-acceptance.sha256'
    Write-TestAscii $acceptanceSidecar "$acceptanceHash  containment-acceptance.json`n"
    return [pscustomobject]@{Root=$fixture;Installer=$installer;Identity=$identityPath;IdentitySidecar=$identitySidecar;Acceptance=$acceptancePath;AcceptanceSidecar=$acceptanceSidecar;Diagnostic=$diagnostic}
}

function Invoke-Verifier {
    param([object]$Fixture,[switch]$VerifyEvidenceOnly)
    $arguments=@('-NoProfile','-ExecutionPolicy','Bypass','-File',$VerifierPath,'-InstallerPath',$Fixture.Installer,'-CandidateIdentityPath',$Fixture.Identity,'-AcceptancePath',$Fixture.Acceptance,'-AcceptanceSidecarPath',$Fixture.AcceptanceSidecar)
    if($VerifyEvidenceOnly){$arguments += '-VerifyEvidenceOnly'}
    $saved=$ErrorActionPreference
    try{
        $ErrorActionPreference='Continue'
        $output=@(& $WindowsPowerShell @arguments 2>&1)
        $exitCode=$LASTEXITCODE
    }finally{$ErrorActionPreference=$saved}
    return [pscustomobject]@{ExitCode=$exitCode;Text=($output -join "`n");Output=$output}
}

function Refresh-AcceptancePair {
    param([object]$Fixture,[object]$Record)
    Write-TestUtf8NoBom $Fixture.Acceptance (ConvertTo-TestCanonicalJson $Record)
    $hash=Get-TestSha256 $Fixture.Acceptance
    Write-TestAscii $Fixture.AcceptanceSidecar "$hash  containment-acceptance.json`n"
}

function Invoke-Test {
    param([string]$Name,[scriptblock]$Body)
    & $Body
    $script:TestsPassed++
    Write-Host "PASS: $Name"
}

function Test-StaticRollbackContract {
    $source=Get-Content -LiteralPath $VerifierPath -Raw
    [Management.Automation.Language.Token[]]$tokens=$null
    [Management.Automation.Language.ParseError[]]$errors=$null
    [void][Management.Automation.Language.Parser]::ParseFile($VerifierPath,[ref]$tokens,[ref]$errors)
    Assert-Equal $errors.Count 0 'Rollback verifier has parse errors.'
    $lines=@(Get-Content -LiteralPath $VerifierPath)
    $paramEnd=0
    if($lines[0]-match '^param\('){for($i=0;$i-lt$lines.Count;$i++){if($lines[$i]-eq')'){$paramEnd=$i;break}}}
    $executables=@($lines[($paramEnd+1)..($lines.Count-1)]|Where-Object{$_.Trim()-and-not$_.Trim().StartsWith('#')})
    Assert-Equal $executables[0].Trim() 'Set-StrictMode -Version Latest' 'Rollback strict-mode line drifted.'
    Assert-Equal $executables[1].Trim() '$ErrorActionPreference = ''Stop''' 'Rollback error preference line drifted.'
    foreach($parameter in @('InstallerPath','CandidateIdentityPath','AcceptancePath','AcceptanceSidecarPath','VerifyEvidenceOnly')){Assert-Contains $source $parameter 'Rollback parameter missing.'}
    foreach($forbidden in @('Start-Process','Remove-Item','Move-Item','Copy-Item','Stop-Process','New-Item','Set-Content','Add-Content','Out-File')){Assert-False $source.Contains($forbidden) "Rollback verifier contains mutating command: $forbidden"}
}

function Test-SuccessAndReadOnlyModes {
    param([string]$Root)
    $fixture=New-RollbackFixture $Root
    $before=Get-TestTreeIdentity $fixture.Root
    $normal=Invoke-Verifier $fixture
    Assert-Equal $normal.ExitCode 0 "Rollback verifier rejected valid retained acceptance: $($normal.Text)"
    $after=Get-TestTreeIdentity $fixture.Root
    Assert-Equal $after $before 'Rollback verification mutated retained evidence.'
    $evidenceOnly=Invoke-Verifier $fixture -VerifyEvidenceOnly
    Assert-Equal $evidenceOnly.ExitCode 0 "Rollback -VerifyEvidenceOnly rejected valid retained acceptance: $($evidenceOnly.Text)"
    Assert-Equal (Get-TestTreeIdentity $fixture.Root) $before 'Rollback -VerifyEvidenceOnly mutated retained evidence.'
}

function Test-DigestAndIdentityFailures {
    param([string]$Root)
    $fixture=New-RollbackFixture $Root
    Write-TestAscii $fixture.Installer 'changed-installer'
    $changed=Invoke-Verifier $fixture
    Assert-True ($changed.ExitCode-ne0) 'Changed installer was eligible for rollback.'
    Assert-Contains $changed.Text 'installer' 'Changed-installer denial lacked context.'

    $fixture=New-RollbackFixture $Root
    Write-TestUtf8NoBom $fixture.Identity ((Get-Content -Raw $fixture.Identity)+' ')
    $changed=Invoke-Verifier $fixture
    Assert-True ($changed.ExitCode-ne0) 'Changed candidate identity was eligible for rollback.'
    Assert-Contains $changed.Text 'identity' 'Changed-identity denial lacked context.'

    $fixture=New-RollbackFixture $Root
    Write-TestAscii $fixture.IdentitySidecar "$('0'*64)  containment-candidate.json`n"
    $changed=Invoke-Verifier $fixture
    Assert-True ($changed.ExitCode-ne0) 'Corrupt candidate sidecar was eligible for rollback.'
    Assert-Contains $changed.Text 'sidecar' 'Candidate-sidecar denial lacked context.'

    $fixture=New-RollbackFixture $Root
    Write-TestAscii $fixture.AcceptanceSidecar "$('0'*64)  containment-acceptance.json`n"
    $changed=Invoke-Verifier $fixture
    Assert-True ($changed.ExitCode-ne0) 'Corrupt acceptance sidecar was eligible for rollback.'
    Assert-Contains $changed.Text 'sidecar' 'Acceptance-sidecar denial lacked context.'
}

function Test-AcceptanceStateFailures {
    param([string]$Root)
    $fixture=New-RollbackFixture $Root
    Remove-Item -LiteralPath $fixture.Acceptance -Force
    $result=Invoke-Verifier $fixture
    Assert-True ($result.ExitCode-ne0) 'Missing acceptance was eligible for rollback.'

    $fixture=New-RollbackFixture $Root
    Write-TestUtf8NoBom (Join-Path $fixture.Root 'containment-failure.json') '{"status":"failed"}'
    $result=Invoke-Verifier $fixture
    Assert-True ($result.ExitCode-ne0) 'Failure diagnostic alongside acceptance was eligible for rollback.'
    Assert-Contains $result.Text 'failure' 'Failure-diagnostic denial lacked context.'

    $fixture=New-RollbackFixture $Root
    $record=Get-Content -Raw $fixture.Acceptance|ConvertFrom-Json
    $record.success=$false
    $record.validator_result.success=$false
    $record.validator_result.status='failed'
    Refresh-AcceptancePair $fixture $record
    $result=Invoke-Verifier $fixture
    Assert-True ($result.ExitCode-ne0) 'success:false acceptance was eligible for rollback.'
    Assert-Contains $result.Text 'success' 'success:false denial lacked context.'

    $acceptanceTypeCases=@(
        [ordered]@{label='schema_version';context='acceptance';mutate={param($value)$value.schema_version='1'}},
        [ordered]@{label='success';context='success';mutate={param($value)$value.success='false'}},
        [ordered]@{label='validator_result.success';context='validator';mutate={param($value)$value.validator_result.success='false'}},
        [ordered]@{label='containment_hold.activated';context='containment hold';mutate={param($value)$value.containment_hold.activated=0}},
        [ordered]@{label='restoration_verified';context='acceptance';mutate={param($value)$value.restoration_verified='false'}},
        [ordered]@{label='quiescence.preflight_quiet';context='quiescence';mutate={param($value)$value.quiescence.preflight_quiet='false'}},
        [ordered]@{label='quiescence.final_quiet';context='quiescence';mutate={param($value)$value.quiescence.final_quiet='false'}},
        [ordered]@{label='startup_isolation.control_fired';context='startup isolation';mutate={param($value)$value.startup_isolation.control_fired='false'}},
        [ordered]@{label='startup_isolation.installed_sanitized';context='startup isolation';mutate={param($value)$value.startup_isolation.installed_sanitized='false'}},
        [ordered]@{label='startup_isolation.installer_sanitized';context='startup isolation';mutate={param($value)$value.startup_isolation.installer_sanitized='false'}},
        [ordered]@{label='startup_isolation.external_hits_absent';context='startup isolation';mutate={param($value)$value.startup_isolation.external_hits_absent='false'}},
        [ordered]@{label='startup_isolation.PYTHONUSERBASE_absent';context='startup isolation';mutate={param($value)$value.startup_isolation.PYTHONUSERBASE_absent='false'}},
        [ordered]@{label='startup_isolation.PYTHONNOUSERSITE';context='environment';mutate={param($value)$value.startup_isolation.PYTHONNOUSERSITE=1}},
        [ordered]@{label='discovery.default';context='discovery';mutate={param($value)$value.discovery.default='422'}},
        [ordered]@{label='discovery.contained_names_absent';context='contained names';mutate={param($value)$value.discovery.contained_names_absent='false'}},
        [ordered]@{label='transport.count';context='transport';mutate={param($value)$value.transport.count='36'}},
        [ordered]@{label='internal.count';context='internal';mutate={param($value)$value.internal.count='164'}},
        [ordered]@{label='scenarios.rhino.success';context='rhino scenario';mutate={param($value)$value.scenarios.rhino.success='false'}},
        [ordered]@{label='scenarios.grasshopper.restoration_verified';context='grasshopper scenario';mutate={param($value)$value.scenarios.grasshopper.restoration_verified='false'}},
        [ordered]@{label='scenarios.rhino.telemetry_delta';context='rhino scenario';mutate={param($value)$value.scenarios.rhino.telemetry_delta='0'}},
        [ordered]@{label='post_run_artifact_snapshot.verified';context='post-run';mutate={param($value)$value.post_run_artifact_snapshot.verified='false'}},
        [ordered]@{label='diagnostics[0].size';context='diagnostic';mutate={param($value)$value.diagnostics[0].size=[string]$value.diagnostics[0].size}}
    )
    foreach($case in $acceptanceTypeCases){
        $fixture=New-RollbackFixture $Root
        $record=Get-Content -Raw $fixture.Acceptance|ConvertFrom-Json
        $mutate=$case.mutate
        & $mutate $record
        Refresh-AcceptancePair $fixture $record
        $result=Invoke-Verifier $fixture
        Assert-True ($result.ExitCode-ne0) "String-coercible rollback acceptance $($case.label) was eligible."
        Assert-Contains $result.Text $case.context "String-coercible rollback denial for $($case.label) lacked context."
    }

    $fixture=New-RollbackFixture $Root
    $record=Get-Content -Raw $fixture.Acceptance|ConvertFrom-Json
    $record.validator_result.success=$false
    $record.validator_result.status='failed'
    Refresh-AcceptancePair $fixture $record
    $result=Invoke-Verifier $fixture
    Assert-True ($result.ExitCode-ne0) 'Failed validator result was eligible for rollback.'

    $fixture=New-RollbackFixture $Root
    $record=Get-Content -Raw $fixture.Acceptance|ConvertFrom-Json
    $record.containment_hold.activated=$true
    $record.containment_hold.receipt_path='C:\hold\containment-hold.json'
    $record.containment_hold.receipt_sha256='6'*64
    Refresh-AcceptancePair $fixture $record
    $result=Invoke-Verifier $fixture
    Assert-True ($result.ExitCode-ne0) 'Acceptance with activated hold was eligible for rollback.'

    $fixture=New-RollbackFixture $Root
    Write-TestAscii (Join-Path $fixture.Root 'containment-hold.sha256') "$('7'*64)  containment-hold.json`n"
    $result=Invoke-Verifier $fixture
    Assert-True ($result.ExitCode-ne0) 'Acceptance beside a retained hold sidecar was eligible for rollback.'
    Assert-Contains $result.Text 'hold' 'Hold-sidecar denial lacked context.'
}

function Test-MutableEvidenceAndCandidateOnlyFailures {
    param([string]$Root)
    $fixture=New-RollbackFixture $Root
    Write-TestUtf8NoBom $fixture.Diagnostic '{"retained":false}'
    $result=Invoke-Verifier $fixture
    Assert-True ($result.ExitCode-ne0) 'Mutable diagnostic evidence was eligible for rollback.'
    Assert-Contains $result.Text 'diagnostic' 'Mutable-evidence denial lacked context.'

    $fixture=New-RollbackFixture $Root
    Remove-Item -LiteralPath $fixture.Acceptance,$fixture.AcceptanceSidecar -Force
    $result=Invoke-Verifier $fixture
    Assert-True ($result.ExitCode-ne0) 'Candidate identity alone was eligible for rollback.'

    $fixture=New-RollbackFixture $Root
    $other=Join-Path $Root ([guid]::NewGuid().ToString('N'))
    [IO.Directory]::CreateDirectory($other)|Out-Null
    $copied=Join-Path $other 'containment-acceptance.json'
    $copiedSidecar=Join-Path $other 'containment-acceptance.sha256'
    Copy-Item $fixture.Acceptance $copied
    Copy-Item $fixture.AcceptanceSidecar $copiedSidecar
    $copyFixture=[pscustomobject]@{Installer=$fixture.Installer;Identity=$fixture.Identity;Acceptance=$copied;AcceptanceSidecar=$copiedSidecar}
    $result=Invoke-Verifier $copyFixture
    Assert-True ($result.ExitCode-ne0) 'Relocated/unbound acceptance evidence was eligible for rollback.'
}

function Test-NormallyNonterminatingErrorStopsNextStage {
    $reached=$false
    Assert-ThrowsLike {
        Invoke-RollbackVerificationStages -Stages @(
            [ordered]@{name='injected';body={Write-Error 'rollback injected normally nonterminating error'}},
            [ordered]@{name='next';body={$script:RollbackUnexpectedStage=$true}}
        )
    } 'normally nonterminating' 'Rollback did not fail fast on Write-Error.'
    Assert-False ([bool](Get-Variable -Name RollbackUnexpectedStage -Scope Script -ErrorAction SilentlyContinue)) 'Rollback reached stage after Write-Error.'
}

. $VerifierPath

$runRoot=Join-Path $env:TEMP ("rook-t10-rollback-tests-"+[guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($runRoot)|Out-Null
$timer=[Diagnostics.Stopwatch]::StartNew()
try{
    Invoke-Test 'static PS5.1 and read-only verifier contract' {Test-StaticRollbackContract}
    Invoke-Test 'immutable installer plus retained acceptance succeeds read-only' {Test-SuccessAndReadOnlyModes $runRoot}
    Invoke-Test 'installer, identity, and both sidecar drifts fail closed' {Test-DigestAndIdentityFailures $runRoot}
    Invoke-Test 'missing/failure/unsuccessful/held acceptance states fail closed' {Test-AcceptanceStateFailures $runRoot}
    Invoke-Test 'mutable, relocated, or candidate-only evidence fails closed' {Test-MutableEvidenceAndCandidateOnlyFailures $runRoot}
    Invoke-Test 'normally nonterminating error stops rollback stages' {Test-NormallyNonterminatingErrorStopsNextStage}
    $timer.Stop()
    Write-Host ("Task 10 rollback tests passed: {0} tests in {1:N2}s." -f $script:TestsPassed,$timer.Elapsed.TotalSeconds)
}finally{
    if($timer.IsRunning){$timer.Stop()}
    Remove-TestTree $runRoot
}
