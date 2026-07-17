param(
    [string]$InstallerPath,
    [string]$CandidateIdentityPath,
    [string]$AcceptancePath,
    [string]$AcceptanceSidecarPath,
    [switch]$VerifyEvidenceOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function ConvertTo-RollbackCanonicalJson {
    param([AllowNull()][object]$Value)

    if ($null -eq $Value) { return 'null' }
    if ($Value -is [bool]) {
        if ($Value) { return 'true' }
        return 'false'
    }
    if ($Value -is [string] -or $Value -is [char]) {
        return ConvertTo-Json -InputObject ([string]$Value) -Compress
    }
    if ($Value -is [byte] -or $Value -is [sbyte] -or
        $Value -is [int16] -or $Value -is [uint16] -or
        $Value -is [int32] -or $Value -is [uint32] -or
        $Value -is [int64] -or $Value -is [uint64] -or
        $Value -is [single] -or $Value -is [double] -or
        $Value -is [decimal]) {
        return [Convert]::ToString(
            $Value,
            [Globalization.CultureInfo]::InvariantCulture
        )
    }
    if ($Value -is [Collections.IDictionary]) {
        [string[]]$keys = @($Value.Keys | ForEach-Object { [string]$_ })
        [Array]::Sort($keys, [StringComparer]::Ordinal)
        $parts = foreach ($key in $keys) {
            (ConvertTo-Json -InputObject $key -Compress) + ':' +
                (ConvertTo-RollbackCanonicalJson -Value ($Value[$key]))
        }
        return '{' + ($parts -join ',') + '}'
    }
    if ($Value -is [pscustomobject]) {
        $mapping = [ordered]@{}
        foreach ($property in $Value.PSObject.Properties) {
            $mapping[$property.Name] = $property.Value
        }
        return ConvertTo-RollbackCanonicalJson -Value $mapping
    }
    if ($Value -is [Collections.IEnumerable]) {
        $items = foreach ($item in $Value) {
            ConvertTo-RollbackCanonicalJson -Value $item
        }
        return '[' + ($items -join ',') + ']'
    }
    throw "unsupported canonical JSON value: $($Value.GetType().FullName)"
}

function Get-RollbackSha256 {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "required retained file is missing: $Path"
    }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Test-RollbackJsonInteger {
    param([AllowNull()][object]$Value)

    return ($Value -is [byte] -or $Value -is [sbyte] -or
        $Value -is [int16] -or $Value -is [uint16] -or
        $Value -is [int32] -or $Value -is [uint32] -or
        $Value -is [int64] -or $Value -is [uint64])
}

function Assert-RollbackHex {
    param(
        [AllowNull()][object]$Value,
        [int]$Length,
        [string]$Label
    )

    $text = [string]$Value
    if ($text -cnotmatch "^[0-9a-f]{$Length}$") {
        throw "$Label is not lowercase $Length-hex"
    }
    return $text
}

function Get-RollbackCanonicalPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [ValidateSet('Leaf', 'Container')][string]$Kind,
        [string]$Label
    )

    if (-not [IO.Path]::IsPathRooted($Path)) {
        throw "$Label must be absolute"
    }
    if (-not (Test-Path -LiteralPath $Path -PathType $Kind)) {
        throw "$Label is missing: $Path"
    }
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    $item = Get-Item -LiteralPath $resolved -Force
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "$Label may not be a reparse point: $resolved"
    }
    return $resolved
}

function Assert-RollbackPathEqual {
    param([string]$Actual, [string]$Expected, [string]$Label)

    if (-not [string]::Equals(
        [IO.Path]::GetFullPath($Actual),
        [IO.Path]::GetFullPath($Expected),
        [StringComparison]::OrdinalIgnoreCase
    )) {
        throw "$Label path does not match retained acceptance"
    }
}

function Read-RollbackCanonicalJson {
    param([string]$Path, [string]$Label)

    $bytes = [IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -ge 3 -and
        $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        throw "$Label contains a UTF-8 BOM"
    }
    $text = [Text.UTF8Encoding]::new($false, $true).GetString($bytes)
    try {
        $record = $text | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        throw "$Label is not valid JSON: $($_.Exception.Message)"
    }
    $canonical = ConvertTo-RollbackCanonicalJson -Value $record
    if ($text -cne $canonical) {
        throw "$Label bytes are not canonical JSON"
    }
    return $record
}

function Assert-RollbackSidecar {
    param(
        [string]$SidecarPath,
        [string]$TargetPath,
        [string]$Label
    )

    $sidecar = Get-RollbackCanonicalPath -Path $SidecarPath -Kind Leaf -Label "$Label sidecar"
    $digest = Get-RollbackSha256 -Path $TargetPath
    $expected = "$digest  $([IO.Path]::GetFileName($TargetPath))`n"
    $actualBytes = [IO.File]::ReadAllBytes($sidecar)
    $actual = [Text.Encoding]::ASCII.GetString($actualBytes)
    if ($actual -cne $expected) {
        throw "$Label sidecar does not match retained bytes"
    }
    return [ordered]@{
        path = $sidecar
        sha256 = Get-RollbackSha256 -Path $sidecar
        target_sha256 = $digest
    }
}

function Resolve-RollbackEvidenceArtifact {
    param(
        [string]$EvidenceDirectory,
        [AllowNull()][object]$RelativePath,
        [string]$Label
    )

    $relative = [string]$RelativePath
    if ([string]::IsNullOrWhiteSpace($relative) -or
        [IO.Path]::IsPathRooted($relative) -or
        $relative -match '(^|[\\/])\.\.([\\/]|$)') {
        throw "$Label has an unsafe relative path"
    }
    $rootPrefix = [IO.Path]::GetFullPath($EvidenceDirectory).TrimEnd('\') + '\'
    $candidate = [IO.Path]::GetFullPath((Join-Path $EvidenceDirectory $relative))
    if (-not $candidate.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "$Label escapes retained evidence"
    }
    return Get-RollbackCanonicalPath -Path $candidate -Kind Leaf -Label $Label
}

function Assert-RollbackIndexedRecords {
    param(
        [AllowNull()][object]$Container,
        [int]$ExpectedCount,
        [string]$Label
    )

    if ($Container.count -isnot [int] -or $Container.count -ne $ExpectedCount) {
        throw "$Label count does not equal $ExpectedCount"
    }
    $records = @($Container.records)
    if ($records.Count -ne $ExpectedCount) {
        throw "$Label retained record count does not equal $ExpectedCount"
    }
    for ($index = 0; $index -lt $records.Count; $index++) {
        $record = $records[$index]
        $recordIndex = $record.PSObject.Properties['index'].Value
        $recordValid = $record.PSObject.Properties['valid'].Value
        if (-not ($recordIndex -is [int]) -or
            -not $recordIndex.Equals($index) -or
            -not ($recordValid -is [bool]) -or
            -not $recordValid) {
            throw "$Label record set is incomplete or invalid at index $index (record=$(ConvertTo-Json -InputObject $record -Compress), indexType=$($recordIndex.GetType().FullName), indexValue=$recordIndex, validType=$($recordValid.GetType().FullName), validValue=$recordValid)"
        }
    }
}

function Invoke-RollbackVerificationStages {
    param([Parameter(Mandatory = $true)][object[]]$Stages)

    foreach ($stage in $Stages) {
        $name = [string]$stage.name
        try {
            & $stage.body
        }
        catch {
            throw "rollback verification stage '$name' failed: $($_.Exception.Message) at $($_.ScriptStackTrace)"
        }
    }
}

function Test-ContainmentRollbackEligibility {
    param(
        [Parameter(Mandatory = $true)][string]$Installer,
        [Parameter(Mandatory = $true)][string]$CandidateIdentity,
        [Parameter(Mandatory = $true)][string]$Acceptance,
        [Parameter(Mandatory = $true)][string]$AcceptanceSidecar
    )

    $state = [ordered]@{}
    Invoke-RollbackVerificationStages -Stages @(
        [ordered]@{ name = 'paths'; body = {
            $state.installer_path = Get-RollbackCanonicalPath -Path $Installer -Kind Leaf -Label 'installer'
            $state.identity_path = Get-RollbackCanonicalPath -Path $CandidateIdentity -Kind Leaf -Label 'candidate identity'
            $state.acceptance_path = Get-RollbackCanonicalPath -Path $Acceptance -Kind Leaf -Label 'acceptance'
            $state.acceptance_sidecar_path = Get-RollbackCanonicalPath -Path $AcceptanceSidecar -Kind Leaf -Label 'acceptance sidecar'
            $state.evidence_directory = Split-Path -Parent $state.acceptance_path
            Assert-RollbackPathEqual -Actual (Split-Path -Parent $state.acceptance_sidecar_path) -Expected $state.evidence_directory -Label 'acceptance sidecar'
            if (Test-Path -LiteralPath (Join-Path $state.evidence_directory 'containment-failure.json') -PathType Leaf) {
                throw 'failure diagnostic is present beside acceptance'
            }
            if (Test-Path -LiteralPath (Join-Path $state.evidence_directory 'containment-failure.sha256') -PathType Leaf) {
                throw 'failure sidecar is present beside acceptance'
            }
        }}
        [ordered]@{ name = 'canonical-records'; body = {
            $state.acceptance_sidecar = Assert-RollbackSidecar -SidecarPath $state.acceptance_sidecar_path -TargetPath $state.acceptance_path -Label 'acceptance'
            $state.acceptance = Read-RollbackCanonicalJson -Path $state.acceptance_path -Label 'acceptance'
            $state.identity = Read-RollbackCanonicalJson -Path $state.identity_path -Label 'candidate identity'
            if ($state.identity.schema_version -isnot [int] -or $state.identity.schema_version -ne 1 -or
                $state.identity.non_publishable -isnot [bool] -or -not $state.identity.non_publishable) {
                throw 'candidate identity is not a non-publishable schema 1 record'
            }
            $candidateSidecar = [string]$state.acceptance.candidate.sidecar_path
            $state.identity_sidecar_path = Get-RollbackCanonicalPath -Path $candidateSidecar -Kind Leaf -Label 'candidate identity sidecar'
            $state.identity_sidecar = Assert-RollbackSidecar -SidecarPath $state.identity_sidecar_path -TargetPath $state.identity_path -Label 'candidate identity'
        }}
        [ordered]@{ name = 'identity-bindings'; body = {
            Assert-RollbackPathEqual -Actual ([string]$state.acceptance.candidate.identity_path) -Expected $state.identity_path -Label 'candidate identity'
            Assert-RollbackPathEqual -Actual ([string]$state.acceptance.candidate.installer_path) -Expected $state.installer_path -Label 'installer'
            $identityDigest = Get-RollbackSha256 -Path $state.identity_path
            $installerDigest = Get-RollbackSha256 -Path $state.installer_path
            if ((Assert-RollbackHex $state.acceptance.candidate.identity_sha256 64 'acceptance candidate identity digest') -cne $identityDigest) {
                throw 'candidate identity hash does not match acceptance'
            }
            if ((Assert-RollbackHex $state.acceptance.candidate.sidecar_sha256 64 'acceptance candidate sidecar digest') -cne $state.identity_sidecar.sha256) {
                throw 'candidate identity sidecar hash does not match acceptance'
            }
            if ((Assert-RollbackHex $state.acceptance.candidate.installer_sha256 64 'acceptance installer digest') -cne $installerDigest) {
                throw 'installer hash does not match acceptance'
            }
            if ((Assert-RollbackHex $state.identity.installer.sha256 64 'candidate installer digest') -cne $installerDigest) {
                throw 'installer hash does not match candidate identity'
            }
            $identityInstaller = [IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $state.identity_path) ([string]$state.identity.installer.relative_path)))
            Assert-RollbackPathEqual -Actual $identityInstaller -Expected $state.installer_path -Label 'candidate installer'
            foreach ($source in @('rook', 'chirp')) {
                $identitySha = Assert-RollbackHex $state.identity.sources.$source.sha 40 "$source source SHA"
                $acceptedSha = Assert-RollbackHex $state.acceptance.candidate."${source}_sha" 40 "accepted $source source SHA"
                if ($identitySha -cne $acceptedSha) {
                    throw "$source source SHA does not match acceptance"
                }
            }
        }}
        [ordered]@{ name = 'successful-acceptance'; body = {
            if ($state.acceptance.schema_version -isnot [int] -or $state.acceptance.schema_version -ne 1 -or
                $state.acceptance.success -isnot [bool] -or -not $state.acceptance.success) {
                throw 'acceptance does not have fixed success true'
            }
            if ($state.acceptance.validator_result.success -isnot [bool] -or
                -not $state.acceptance.validator_result.success -or
                $state.acceptance.validator_result.status -isnot [string] -or
                $state.acceptance.validator_result.status -cne 'passed') {
                throw 'successful validator result is missing'
            }
            [void](Assert-RollbackHex $state.acceptance.validator.sha256 64 'validator digest')
            if ($state.acceptance.containment_hold.activated -isnot [bool] -or
                $state.acceptance.containment_hold.activated -or
                $null -ne $state.acceptance.containment_hold.receipt_path -or
                $null -ne $state.acceptance.containment_hold.receipt_sha256) {
                throw 'acceptance has an activated containment hold'
            }
            foreach ($holdName in @('containment-hold.json','containment-hold.sha256')) {
                if (Test-Path -LiteralPath (Join-Path $state.evidence_directory $holdName) -PathType Leaf) {
                    throw 'containment hold receipt or sidecar is present beside acceptance'
                }
            }
            if ($state.acceptance.restoration_verified -isnot [bool] -or
                -not $state.acceptance.restoration_verified -or
                $state.acceptance.quiescence.preflight_quiet -isnot [bool] -or
                -not $state.acceptance.quiescence.preflight_quiet -or
                $state.acceptance.quiescence.final_quiet -isnot [bool] -or
                -not $state.acceptance.quiescence.final_quiet) {
                throw 'acceptance restoration or quiescence is unverified'
            }
            foreach ($name in @('control_fired','installed_sanitized','installer_sanitized','external_hits_absent','PYTHONUSERBASE_absent')) {
                if ($state.acceptance.startup_isolation.$name -isnot [bool] -or
                    -not $state.acceptance.startup_isolation.$name) {
                    throw "acceptance startup isolation is incomplete: $name"
                }
            }
            if ($state.acceptance.startup_isolation.PYTHONNOUSERSITE -isnot [string] -or
                $state.acceptance.startup_isolation.PYTHONNOUSERSITE -cne '1') {
                throw 'acceptance startup isolation environment is incomplete'
            }
            $expectedDiscovery = [ordered]@{ default = 422; full = 422; lean = 20; readonly = 148; interactive_full = 425 }
            foreach ($name in $expectedDiscovery.Keys) {
                if ($state.acceptance.discovery.$name -isnot [int] -or
                    $state.acceptance.discovery.$name -ne $expectedDiscovery[$name]) {
                    throw "acceptance discovery count drift: $name"
                }
            }
            if ($state.acceptance.discovery.contained_names_absent -isnot [bool] -or
                -not $state.acceptance.discovery.contained_names_absent) {
                throw 'contained names remain discoverable'
            }
            Assert-RollbackIndexedRecords -Container $state.acceptance.transport -ExpectedCount 36 -Label 'transport'
            Assert-RollbackIndexedRecords -Container $state.acceptance.internal -ExpectedCount 164 -Label 'internal'
            foreach ($scenario in @('rhino', 'grasshopper')) {
                $entry = $state.acceptance.scenarios.$scenario
                if ($entry.success -isnot [bool] -or -not $entry.success -or
                    $entry.restoration_verified -isnot [bool] -or -not $entry.restoration_verified -or
                    $entry.telemetry_delta -isnot [int] -or $entry.telemetry_delta -ne 0) {
                    throw "$scenario scenario is not safely restored"
                }
            }
            if ($state.acceptance.post_run_artifact_snapshot.verified -isnot [bool] -or
                -not $state.acceptance.post_run_artifact_snapshot.verified) {
                throw 'post-run candidate artifact snapshot is unverified'
            }
        }}
        [ordered]@{ name = 'retained-diagnostics'; body = {
            $diagnostics = @($state.acceptance.diagnostics)
            if ($diagnostics.Count -eq 0) {
                throw 'acceptance has no retained diagnostic inventory'
            }
            $seen = @{}
            foreach ($diagnostic in $diagnostics) {
                $relative = [string]$diagnostic.relative_path
                if ($seen.ContainsKey($relative)) {
                    throw "duplicate diagnostic path: $relative"
                }
                $seen[$relative] = $true
                $path = Resolve-RollbackEvidenceArtifact -EvidenceDirectory $state.evidence_directory -RelativePath $relative -Label 'diagnostic artifact'
                $item = Get-Item -LiteralPath $path -Force
                if (-not (Test-RollbackJsonInteger $diagnostic.size) -or
                    [long]$diagnostic.size -ne [long]$item.Length -or
                    (Assert-RollbackHex $diagnostic.sha256 64 'diagnostic digest') -cne (Get-RollbackSha256 -Path $path)) {
                    throw "diagnostic artifact hash or size drift: $relative"
                }
            }
        }}
    )

    return [pscustomobject]@{
        eligible = $true
        installer_sha256 = Get-RollbackSha256 -Path $state.installer_path
        candidate_identity_sha256 = Get-RollbackSha256 -Path $state.identity_path
        acceptance_sha256 = Get-RollbackSha256 -Path $state.acceptance_path
        evidence_only = [bool]$VerifyEvidenceOnly
    }
}

function Invoke-ContainmentRollbackVerifierMain {
    if ([string]::IsNullOrWhiteSpace($InstallerPath) -or
        [string]::IsNullOrWhiteSpace($CandidateIdentityPath) -or
        [string]::IsNullOrWhiteSpace($AcceptancePath) -or
        [string]::IsNullOrWhiteSpace($AcceptanceSidecarPath)) {
        throw 'InstallerPath, CandidateIdentityPath, AcceptancePath, and AcceptanceSidecarPath are required'
    }
    $result = Test-ContainmentRollbackEligibility `
        -Installer $InstallerPath `
        -CandidateIdentity $CandidateIdentityPath `
        -Acceptance $AcceptancePath `
        -AcceptanceSidecar $AcceptanceSidecarPath
    Write-Host ("containment-safe rollback eligible: installer={0} acceptance={1}" -f $result.installer_sha256, $result.acceptance_sha256)
}

if ($MyInvocation.InvocationName -ne '.') {
    try {
        Invoke-ContainmentRollbackVerifierMain
        exit 0
    }
    catch {
        [Console]::Error.WriteLine("containment-safe rollback denied: $($_.Exception.Message)")
        exit 1
    }
}
