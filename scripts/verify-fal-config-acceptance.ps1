[CmdletBinding()]
param([string]$FreezeManifest, [string]$Cases, [string]$Evidence, [string]$Report)
$ErrorActionPreference = 'Stop'

function Test-FalNumber($Value) {
    if ($null -eq $Value -or $Value.GetType() -notin @([byte],[sbyte],[int16],[uint16],[int32],[uint32],[int64],[uint64],[single],[double],[decimal])) { return $false }
    try { $null=[decimal]$Value; return $true } catch { return $false }
}
function Get-FalPropertyNames($Value) {
    if ($Value -is [Collections.IDictionary]) { return @($Value.Keys) }
    if ($Value -is [pscustomobject]) { return @($Value.PSObject.Properties.Name) }
    return @()
}
function Get-FalNumberIdentity($Value) {
    $format=if ($Value -is [double] -or $Value -is [single]) { 'R' } else { 'G' }
    $text=$Value.ToString($format,[Globalization.CultureInfo]::InvariantCulture)
    if ($text -notmatch '^(-?)([0-9]+)(?:\.([0-9]+))?(?:[eE]([+-]?[0-9]+))?$') { throw 'Unsupported numeric evidence.' }
    $sign=$Matches[1]; $fraction=$Matches[3]; $exponent=if ($Matches[4]) { [int]$Matches[4] } else { 0 }
    $digits=($Matches[2]+$fraction).TrimStart('0'); $exponent-=$fraction.Length
    if (!$digits) { return '0' }
    $trimmed=$digits.TrimEnd('0'); $exponent+=($digits.Length-$trimmed.Length)
    return $sign+$trimmed+'e'+$exponent.ToString([Globalization.CultureInfo]::InvariantCulture)
}
function Test-FalJsonEqual($Left,$Right) {
    if ($null -eq $Left -or $null -eq $Right) { return ($null -eq $Left -and $null -eq $Right) }
    if ((Test-FalNumber $Left) -or (Test-FalNumber $Right)) { return ((Test-FalNumber $Left) -and (Test-FalNumber $Right) -and (Get-FalNumberIdentity $Left) -ceq (Get-FalNumberIdentity $Right)) }
    if ($Left -is [bool] -or $Right -is [bool]) { return ($Left -is [bool] -and $Right -is [bool] -and $Left -eq $Right) }
    if ($Left -is [string] -or $Right -is [string]) { return ($Left -is [string] -and $Right -is [string] -and $Left -ceq $Right) }
    $leftObject=$Left -is [Collections.IDictionary] -or $Left -is [pscustomobject]
    $rightObject=$Right -is [Collections.IDictionary] -or $Right -is [pscustomobject]
    if ($leftObject -or $rightObject) {
        if (!$leftObject -or !$rightObject) { return $false }
        $leftNames=@(Get-FalPropertyNames $Left); $rightNames=@(Get-FalPropertyNames $Right)
        if ($leftNames.Count -ne $rightNames.Count) { return $false }
        foreach ($name in $leftNames) { if ($rightNames -cnotcontains $name -or !(Test-FalJsonEqual $Left.$name $Right.$name)) { return $false } }
        return $true
    }
    if ($Left -is [Collections.IEnumerable] -and $Right -is [Collections.IEnumerable]) {
        $leftItems=@($Left); $rightItems=@($Right)
        if ($leftItems.Count -ne $rightItems.Count) { return $false }
        for ($i=0;$i -lt $leftItems.Count;$i++) { if (!(Test-FalJsonEqual $leftItems[$i] $rightItems[$i])) { return $false } }
        return $true
    }
    return $false
}
function Test-FalControlType($Value,[string]$Type) {
    switch ($Type) {
        'number' { return (Test-FalNumber $Value) }
        'integer' { return ((Test-FalNumber $Value) -and [decimal]$Value -eq [decimal]::Truncate([decimal]$Value)) }
        'boolean' { return ($Value -is [bool]) }
        'enum' { return ($Value -is [string]) }
        'string' { return ($Value -is [string]) }
        default { return $false }
    }
}
function Get-FalAcceptanceIssues($Freeze, $CaseData, $Proof, $Current, [string]$FreezeHash, [string]$CasesHash) {
    $issues = [Collections.Generic.List[string]]::new()
    if ($Freeze.schema_version -ne 1 -or $Freeze.policy -ne 'fal-runtime-freeze-v1') { $issues.Add('Unsupported freeze manifest.') }
    if ($Proof.schema_version -ne 1 -or $Proof.freeze_sha256 -ne $FreezeHash -or $Proof.cases_sha256 -ne $CasesHash) { $issues.Add('Evidence does not identify the frozen runtime and exact case data.') }
    $before = @($Freeze.roots); $after = @($Current.roots)
    if (!$before.Count -or $before.Count -ne $after.Count) { $issues.Add('Frozen root inventory is missing or changed.') }
    foreach ($root in $before) {
        $match = @($after | Where-Object { $_.name -ceq $root.name -and $_.path -ceq $root.path -and $_.kind -ceq $root.kind })
        if ($match.Count -ne 1 -or (ConvertTo-Json -InputObject @($root.files) -Depth 10 -Compress) -cne (ConvertTo-Json -InputObject @($match[0].files) -Depth 10 -Compress)) { $issues.Add("Frozen code added, removed, or modified: $($root.name)") }
    }
    if (!$Proof.reviewer -or !$Proof.reviewed_utc -or [DateTimeOffset]$Proof.reviewed_utc -lt [DateTimeOffset]$Freeze.created_utc) { $issues.Add('Post-freeze reviewer sign-off missing.') }
    if (!$Proof.spend_authorization.maintainer -or !$Proof.spend_authorization.approved_utc -or !(Test-FalNumber $Proof.spend_authorization.cap_usd) -or [decimal]$Proof.spend_authorization.cap_usd -le 0) { $issues.Add('Concrete maintainer spend authorization missing.') }
    $endpoints = @($Proof.endpoints)
    if ($endpoints.Count -ne 2 -or @($endpoints | Where-Object modality -eq image).Count -ne 1 -or @($endpoints | Where-Object modality -eq video).Count -ne 1) { $issues.Add('One image and one video endpoint are required.') }
    if (@($endpoints.model_id | Select-Object -Unique).Count -ne 2 -or @($endpoints.endpoint | Select-Object -Unique).Count -ne 2) { $issues.Add('Held-out endpoint identities must be distinct.') }
    foreach ($endpoint in $endpoints) {
        if (!$endpoint.model_id -or !$endpoint.operation -or !$endpoint.endpoint -or $endpoint.definition_hash -notmatch '^[a-fA-F0-9]{64}$') { $issues.Add('Endpoint identity or definition hash missing.') }
        if (!$endpoint.selected_utc -or [DateTimeOffset]$endpoint.selected_utc -le [DateTimeOffset]$Freeze.created_utc -or @($Freeze.catalog_models) -contains $endpoint.model_id -or @($Freeze.catalog_endpoints) -contains $endpoint.endpoint) { $issues.Add('Endpoint was not held out until after freeze.') }
        if (!$Proof.reviewed_utc -or !$endpoint.selected_utc -or [DateTimeOffset]$endpoint.selected_utc -le [DateTimeOffset]$Proof.reviewed_utc) { $issues.Add('Endpoint selection must follow reviewer sign-off.') }
        if ($endpoint.documentation.url -notmatch '^https://(docs\.)?fal\.ai/' -or !$endpoint.documentation.reviewed_on -or $endpoint.documentation.schema_sha256 -notmatch '^[a-fA-F0-9]{64}$' -or $endpoint.documentation.pricing_sha256 -notmatch '^[a-fA-F0-9]{64}$') { $issues.Add('Official schema/pricing review missing.') }
        $controls = @($endpoint.controls)
        if ($controls.Count -lt 2 -or @($controls | Where-Object { !$_.name -or $_.name -in @('model','prompt','resolution','aspect_ratio','duration_seconds') -or $_.type -notin @('number','integer','boolean','enum','string') }).Count) { $issues.Add('Two concrete provider controls beyond common selectors are required per endpoint.') }
    }
    $types = @($endpoints | ForEach-Object { $_.controls } | ForEach-Object { $_.type })
    if (!(@($types | Where-Object { $_ -in @('number','integer') }).Count) -or !(@($types | Where-Object { $_ -in @('boolean','enum') }).Count)) { $issues.Add('Numeric and boolean/enum control coverage missing.') }
    $jobs = @($Proof.live_jobs)
    if ($jobs.Count -ne 4 -or @($jobs.job_id | Select-Object -Unique).Count -ne 4) { $issues.Add('Incomplete: four distinct successful live jobs are required.') }
    [decimal]$estimatedTotal = 0
    foreach ($endpoint in $endpoints) {
        foreach ($surface in @('panel','mcp')) {
            $selection = @($jobs | Where-Object { $_.model_id -eq $endpoint.model_id -and $_.surface -eq $surface })
            if ($selection.Count -ne 1) { $issues.Add("Missing unique live job for $($endpoint.model_id)/$surface"); continue }
            $job = $selection[0]
            if ($job.mode -ne 'live' -or $job.state -ne 'completed' -or $job.endpoint -ne $endpoint.endpoint -or $job.operation -ne $endpoint.operation -or $job.definition_hash -ne $endpoint.definition_hash -or $job.runtime_sha256 -ne $FreezeHash) { $issues.Add('Live job identity, state, or runtime provenance mismatch.') }
            $guid = [Guid]::Empty
            if (![Guid]::TryParse($job.job_id, [ref]$guid) -or ![Guid]::TryParse($job.artifact_id, [ref]$guid) -or $job.result_mime -notmatch ('^' + $endpoint.modality + '/')) { $issues.Add('Live job/artifact IDs or result MIME missing.') }
            foreach ($field in @('normalized_sha256','payload_sha256','request_sha256')) { if ($job.$field -notmatch '^[a-fA-F0-9]{64}$') { $issues.Add("Missing $field") } }
            if ($job.quote_fingerprint -notmatch '^fal1:[a-fA-F0-9]{64}$' -or !(Test-FalNumber $job.max_estimated_cost_usd) -or [decimal]$job.max_estimated_cost_usd -lt 0) { $issues.Add('Quote/cap evidence missing.') } else { $estimatedTotal += [decimal]$job.max_estimated_cost_usd }
            if (!$job.started_utc -or !$job.completed_utc -or [DateTimeOffset]$job.started_utc -lt [DateTimeOffset]$Proof.spend_authorization.approved_utc -or [DateTimeOffset]$job.started_utc -lt [DateTimeOffset]$endpoint.selected_utc -or [DateTimeOffset]$job.completed_utc -lt [DateTimeOffset]$job.started_utc) { $issues.Add('Live job timestamps invalid.') }
            if ($job.actual_spend.status -notin @('reported','unavailable') -or ($job.actual_spend.status -eq 'reported' -and (!(Test-FalNumber $job.actual_spend.usd) -or [decimal]$job.actual_spend.usd -lt 0))) { $issues.Add('Actual spend must be reported separately, never inferred from an estimate.') }
            foreach ($control in @($endpoint.controls)) { if (@(Get-FalPropertyNames $job.selected_controls) -cnotcontains $control.name -or !(Test-FalControlType $job.selected_controls.($control.name) $control.type)) { $issues.Add('Selected useful control is missing or has the wrong type.') } }
            $case = @($CaseData.cases | Where-Object id -eq $job.case_id)
            if ($case.Count -ne 1 -or $case[0].surface -ne $surface -or $case[0].request.model -ne $job.model_id -or !$case[0].expected.provider_payload) { $issues.Add('Live job is not joined to a generic exact-boundary case.') }
            foreach ($link in @('capture','provenance','artifact')) { if (!$job.$link.path -or $job.$link.sha256 -notmatch '^[a-fA-F0-9]{64}$') { $issues.Add("Missing $link evidence link.") } }
        }
    }
    if ($estimatedTotal -gt [decimal]$Proof.spend_authorization.cap_usd) { $issues.Add('Confirmed job caps exceed authorized total.') }
    foreach ($name in @('native_build','managed_builds','regression','package','installed_mcp','installed_panel','loaded_paths')) {
        $check = @($Proof.qualification | Where-Object name -eq $name)
        if ($check.Count -ne 1 -or $check[0].exit_code -ne 0 -or !$check[0].path -or $check[0].sha256 -notmatch '^[a-fA-F0-9]{64}$') { $issues.Add("Missing recorded qualification: $name") }
    }
    return $issues.ToArray()
}
function Assert-FalEvidenceFile($Link, [string]$EvidenceDirectory) {
    if (!$Link.path -or $Link.sha256 -notmatch '^[a-fA-F0-9]{64}$') { throw 'Invalid evidence file reference.' }
    $path = [IO.Path]::GetFullPath((Join-Path $EvidenceDirectory $Link.path))
    if (!$path.StartsWith($EvidenceDirectory.TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Evidence reference escapes its attempt directory.' }
    if (!(Test-Path -LiteralPath $path -PathType Leaf) -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $Link.sha256) { throw "Evidence file hash mismatch: $($Link.path)" }
    return $path
}
function Assert-FalFrozenFile($Freeze,[string]$RootName,[string]$Path,[string]$Hash) {
    $roots=@($Freeze.roots | Where-Object name -CEQ $RootName)
    if ($roots.Count -ne 1 -or !$Path -or ![IO.Path]::IsPathRooted($Path) -or $Hash -notmatch '^[a-fA-F0-9]{64}$') { throw 'Frozen loaded-file identity is missing.' }
    $root=[IO.Path]::GetFullPath($roots[0].path).TrimEnd('\','/')
    $canonical=[IO.Path]::GetFullPath($Path)
    if (!$canonical.StartsWith($root+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase) -or !(Test-Path -LiteralPath $canonical -PathType Leaf)) { throw 'Loaded file is not inside its frozen runtime root.' }
    $relative=$canonical.Substring($root.Length+1).Replace('\','/')
    $records=@($roots[0].files | Where-Object { $_.path -ceq $relative -and $_.kind -ne 'directory_alias' })
    if ($records.Count -ne 1 -or $records[0].sha256 -ne $Hash -or (Get-FileHash -LiteralPath $canonical).Hash -ne $records[0].sha256) { throw 'Loaded file does not match its exact frozen inventory record.' }
    return $canonical
}
function Invoke-FalConfigAcceptance([string]$FreezeManifest, [string]$Cases, [string]$Evidence, [string]$Report) {
    $issues = [Collections.Generic.List[string]]::new(); $currentPath = $null
    try {
        $freeze = Get-Content -LiteralPath $FreezeManifest -Raw | ConvertFrom-Json
        $caseData = Get-Content -LiteralPath $Cases -Raw | ConvertFrom-Json
        $proof = Get-Content -LiteralPath $Evidence -Raw | ConvertFrom-Json
        if (!(Test-Path -LiteralPath $freeze.qualifier -PathType Leaf) -or (Get-FileHash -LiteralPath $freeze.qualifier -Algorithm SHA256).Hash -ne $freeze.qualifier_sha256) { throw 'Frozen qualifier executable is missing or changed.' }
        # Verify every frozen qualifier dependency before executing that host. A changed
        # Rook.dll must not be allowed to produce its own supposedly matching inventory.
        $hostRoot = @($freeze.roots | Where-Object name -eq 'built/qualifier/net48')
        if ($hostRoot.Count -ne 1 -or !@($hostRoot[0].files).Count) { throw 'Missing frozen qualifier dependency inventory.' }
        $hostFiles = @(Get-ChildItem -LiteralPath $hostRoot[0].path -File -Recurse -Force | Where-Object { $_.FullName -notmatch '[\\/]vision-models[\\/]fal[\\/].+\.json$' })
        if ($hostFiles.Count -ne @($hostRoot[0].files).Count) { throw 'Qualifier dependency file set changed.' }
        foreach ($file in $hostRoot[0].files) {
            $path = Join-Path $hostRoot[0].path $file.path
            if (!(Test-Path -LiteralPath $path -PathType Leaf) -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $file.sha256) { throw 'Frozen qualifier dependency changed.' }
        }
        $currentPath = Join-Path ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($Report))) ('current-freeze-' + [Guid]::NewGuid().ToString('N') + '.json')
        New-Item -ItemType Directory -Path (Split-Path $currentPath) -Force | Out-Null
        & $freeze.qualifier freeze-runtime --repo $freeze.repo --plugin-root $freeze.plugin_root --mcp-root $freeze.mcp_root --out $currentPath | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Cannot enumerate current frozen runtime.' }
        $current = Get-Content -LiteralPath $currentPath -Raw | ConvertFrom-Json
        $freezeHash = (Get-FileHash -LiteralPath $FreezeManifest -Algorithm SHA256).Hash.ToLowerInvariant()
        $caseHash = (Get-FileHash -LiteralPath $Cases -Algorithm SHA256).Hash.ToLowerInvariant()
        foreach ($issue in @(Get-FalAcceptanceIssues $freeze $caseData $proof $current $freezeHash $caseHash)) { $issues.Add($issue) }
        $dir = [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($Evidence))
        foreach ($link in @($proof.qualification) + @($proof.live_jobs | ForEach-Object { $_.capture; $_.provenance; $_.artifact })) { $null = Assert-FalEvidenceFile $link $dir }
        $conformancePath = Assert-FalEvidenceFile $proof.conformance $dir
        $conformance = Get-Content -LiteralPath $conformancePath -Raw | ConvertFrom-Json
        if (!$conformance.offline -or !$conformance.success -or $conformance.cases_sha256 -ne $caseHash -or @($conformance.cases).Count -ne @($caseData.cases).Count -or @($conformance.cases | Where-Object { !$_.passed }).Count) { throw 'Generic conformance report is missing, stale, or failed.' }
        foreach ($job in @($proof.live_jobs)) {
            $row = @($conformance.cases | Where-Object id -eq $job.case_id)
            if ($row.Count -ne 1 -or $row[0].model_id -ne $job.model_id -or $row[0].endpoint -ne $job.endpoint -or $row[0].operation -ne $job.operation -or $row[0].surface -ne $job.surface -or $row[0].request_sha256 -ne $job.request_sha256 -or $row[0].normalized_sha256 -ne $job.normalized_sha256 -or $row[0].payload_sha256 -ne $job.payload_sha256 -or $row[0].definition_hash -ne $job.definition_hash) { throw 'Live job request and normalized input do not match its boundary fixture.' }
            $row=$row[0]
            $capture = Get-Content -LiteralPath (Assert-FalEvidenceFile $job.capture $dir) -Raw | ConvertFrom-Json
            $provenance = Get-Content -LiteralPath (Assert-FalEvidenceFile $job.provenance $dir) -Raw | ConvertFrom-Json
            if ($capture.surface -ne $job.surface -or $capture.request_sha256 -ne $job.request_sha256 -or $capture.normalized_sha256 -ne $job.normalized_sha256 -or $capture.payload_sha256 -ne $job.payload_sha256 -or $provenance.job_id -ne $job.job_id -or $provenance.definition_hash -ne $job.definition_hash -or $provenance.artifact_id -ne $job.artifact_id) { throw 'Capture/provenance join mismatch.' }
            if ($job.quote_fingerprint -cne $row.quote_fingerprint -or !(Test-FalNumber $row.cap_usd) -or !(Test-FalJsonEqual $job.max_estimated_cost_usd $row.cap_usd) -or
                !(Test-FalJsonEqual $capture.confirmation $row.confirmation) -or $capture.confirmation.quote_fingerprint -cne $job.quote_fingerprint -or !(Test-FalJsonEqual $capture.confirmation.max_estimated_cost_usd $job.max_estimated_cost_usd)) { throw 'Job quote/cap does not match the captured confirmed submission.' }
            foreach ($field in @('quote_fingerprint','max_estimated_cost_usd','pricing')) {
                if ($null -eq $capture.quote.$field -or $null -eq $row.quote.$field -or !(Test-FalJsonEqual $capture.quote.$field $row.quote.$field)) { throw 'Captured quote/pricing does not match the boundary fixture.' }
            }
            if ($capture.quote.quote_fingerprint -cne $job.quote_fingerprint -or !(Test-FalNumber $capture.quote.max_estimated_cost_usd) -or [decimal]$capture.confirmation.max_estimated_cost_usd -lt [decimal]$capture.quote.max_estimated_cost_usd) { throw 'Confirmed cap is below its captured quote.' }
            foreach ($name in @(Get-FalPropertyNames $job.selected_controls)) {
                if (@(Get-FalPropertyNames $row.effective_options) -cnotcontains $name -or !(Test-FalJsonEqual $job.selected_controls.$name $row.effective_options.$name)) { throw 'Selected control value/type does not match normalized boundary inputs.' }
            }
            foreach ($field in @('effective_request','effective_options','pricing','media')) {
                if (@(Get-FalPropertyNames $provenance) -cnotcontains $field -or @(Get-FalPropertyNames $row.provenance) -cnotcontains $field -or !(Test-FalJsonEqual $provenance.$field $row.provenance.$field)) { throw 'Saved provenance controls/pricing/media do not match the boundary fixture.' }
            }
            if (!(Test-FalJsonEqual $provenance.effective_request $row.effective_request) -or !(Test-FalJsonEqual $provenance.effective_options $row.effective_options) -or !(Test-FalJsonEqual $provenance.media $row.media) -or !(Test-FalJsonEqual $provenance.pricing $capture.quote.pricing)) { throw 'Saved provenance and captured quote inputs disagree.' }
        }
        $loadedLink = @($proof.qualification | Where-Object name -eq 'loaded_paths')[0]
        $loaded = Get-Content -LiteralPath (Assert-FalEvidenceFile $loadedLink $dir) -Raw | ConvertFrom-Json
        if (!$loaded.process_id -or !$loaded.process_started_utc -or !$loaded.observed_utc -or @($loaded.modules).Count -lt 2) { throw 'Actual loaded module/process evidence missing.' }
        foreach ($moduleName in @('RookNative.rhp','Rook.rhp')) {
            $module = @($loaded.modules | Where-Object name -eq $moduleName)
            if ($module.Count -ne 1 -or !$module[0].version -or [IO.Path]::GetFileName($module[0].path) -cne $moduleName) { throw 'Loaded native/managed module evidence mismatch.' }
            $null=Assert-FalFrozenFile $freeze 'installed/plugin' $module[0].path $module[0].sha256
        }
        $pythonPath=Assert-FalFrozenFile $freeze 'installed/mcp' $loaded.python.path $loaded.python.sha256
        $packagePath=Assert-FalFrozenFile $freeze 'installed/mcp' $loaded.python.package_path $loaded.python.package_sha256
        $expectedPython=[IO.Path]::GetFullPath((Join-Path $freeze.mcp_root 'venv/Scripts/python.exe'))
        $privatePackage=[IO.Path]::GetFullPath((Join-Path $freeze.mcp_root 'venv/Lib/site-packages/rook')).TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar
        if (!$pythonPath.Equals($expectedPython,[StringComparison]::OrdinalIgnoreCase) -or !$packagePath.StartsWith($privatePackage,[StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetFileName($packagePath) -notin @('__init__.py','__init__.pyc')) { throw 'Loaded Python/package origin is not the deployed private Rook environment.' }
        # Even changed files outside compiled roots must be configuration or this attempt's prose.
        $diff = @(& git -C $freeze.repo diff --name-only $freeze.commit HEAD)
        if ($LASTEXITCODE -ne 0) { throw 'Cannot compare commits.' }
        $diff += @(& git -C $freeze.repo ls-files --others --exclude-standard)
        $diff += @(& git -C $freeze.repo diff --name-only HEAD)
        foreach ($path in $diff) { if ($path -notmatch '^src/Rook/Services/Vision/Fal/Models/(.+/)?[^/]+\.json$' -and $path -notmatch '^docs/vision/acceptance/[^/]+\.md$') { $issues.Add("Nonconfiguration source change: $path") } }
    } catch { $issues.Add($_.Exception.Message) }
    finally { if ($currentPath -and (Test-Path -LiteralPath $currentPath)) { Remove-Item -LiteralPath $currentPath } }
    $result = [ordered]@{ schema_version=1; success=($issues.Count -eq 0); status=$(if ($issues.Count) {'incomplete_or_failed'} else {'accepted'}); issues=@($issues.ToArray()); checked_utc=[DateTimeOffset]::UtcNow.ToString('O') }
    New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($Report))) -Force | Out-Null
    $result | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $Report -Encoding utf8
    if ($issues.Count) { Write-Host ($issues -join "`n"); return 1 }; return 0
}
if ($MyInvocation.InvocationName -ne '.') { exit (Invoke-FalConfigAcceptance $FreezeManifest $Cases $Evidence $Report) }
