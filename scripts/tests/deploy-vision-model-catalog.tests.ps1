param([string]$QualificationPath = '')
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$script = Join-Path $repo 'scripts/deploy-vision-model-catalog.ps1'
function Assert-True([bool]$Condition, [string]$Message) { if (-not $Condition) { throw $Message } }
Assert-True (Test-Path -LiteralPath $script) 'Config-only catalog deployment script must exist.'
. $script

# These tests exercise the real filesystem transaction. Only process observation and
# external semantic validation are injected; the CLI is tested separately after build.
$temp = Join-Path ([IO.Path]::GetTempPath()) ('rook-catalog-tests-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp | Out-Null
try {
    $source = Join-Path $temp 'source'
    $plugin = Join-Path $temp 'RookNative'
    New-Item -ItemType Directory -Path $source, $plugin | Out-Null
    '{"schema_version":1,"definitions":[]}' | Set-Content (Join-Path $source 'catalog.json') -Encoding ASCII
    New-Item -ItemType Directory -Path (Join-Path $source 'nested') | Out-Null
    '{}' | Set-Content (Join-Path $source 'nested/future.json') -Encoding ASCII
    'must not copy' | Set-Content (Join-Path $source 'ignored.dll') -Encoding ASCII
    foreach ($runtime in @('net48', 'net7.0', 'net8.0')) {
        $dir = Join-Path $plugin "$runtime/vision-models/fal"
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        '{"schema_version":1,"definitions":[]}' | Set-Content (Join-Path $dir 'catalog.json') -Encoding ASCII
        "old-$runtime" | Set-Content (Join-Path $dir 'old.json') -Encoding ASCII
        'binary' | Set-Content (Join-Path $plugin "$runtime/Rook.rhp") -Encoding ASCII
        'symbols' | Set-Content (Join-Path $plugin "$runtime/Rook.pdb") -Encoding ASCII
        'deps' | Set-Content (Join-Path $plugin "$runtime/Rook.deps.json") -Encoding ASCII
    }
    'native' | Set-Content (Join-Path $plugin 'RookNative.rhp') -Encoding ASCII
    'ui' | Set-Content (Join-Path $plugin 'panel.js') -Encoding ASCII
    'python' | Set-Content (Join-Path $plugin 'server.py') -Encoding ASCII
    'secret' | Set-Content (Join-Path $plugin '.env') -Encoding ASCII
    $stopped = { @() }
    $valid = { param($root, $validator) if (-not (Test-Path -LiteralPath (Join-Path $root 'catalog.json'))) { throw 'manifest missing' } }
    $before = Get-VisionPayloadManifest $plugin
    $result = Invoke-VisionModelCatalogDeploy -CatalogRoot $source -PluginRoot $plugin -ValidatorPath 'injected' -ProcessProbe $stopped -ValidateCatalog $valid
    $count = 0
    foreach ($runtime in @('net48', 'net7.0', 'net8.0')) {
        $dir = Join-Path $plugin "$runtime/vision-models/fal"
        Assert-True (Test-Path -LiteralPath (Join-Path $dir 'nested/future.json')) 'Generic JSON must copy recursively.'
        Assert-True (-not (Test-Path -LiteralPath (Join-Path $dir 'old.json'))) 'Stale definitions must be replaced.'
        Assert-True (-not (Test-Path -LiteralPath (Join-Path $dir 'ignored.dll'))) 'Catalog copy must include JSON only.'
        $count++
    }
    Assert-True ($count -eq 3) 'Generic definitions must reach every runtime.'
    Assert-True ((Get-VisionPayloadManifest $plugin) -ceq $before) 'Config copy must preserve every code payload hash.'
    Assert-True ($result.RestartRequired -and $result.CodeHashesUnchanged) 'Deployment must report restart and verified code parity.'

    $original = @('net48','net7.0','net8.0') | ForEach-Object { Get-VisionCatalogFileManifest (Join-Path $plugin "$_/vision-models/fal") | ConvertTo-Json -Compress }
    $rejected = $false
    try { Invoke-VisionModelCatalogDeploy $source $plugin 'injected' -ProcessProbe $stopped -ValidateCatalog { throw 'invalid catalog' } | Out-Null } catch { $rejected = $_.Exception.Message -like '*invalid catalog*' }
    Assert-True $rejected 'Reject an invalid catalog before copying.'
    $after = @('net48','net7.0','net8.0') | ForEach-Object { Get-VisionCatalogFileManifest (Join-Path $plugin "$_/vision-models/fal") | ConvertTo-Json -Compress }
    Assert-True (($original -join "`n") -ceq ($after -join "`n")) 'Invalid source must leave all catalogs unchanged.'

    'new' | Set-Content (Join-Path $source 'nested/future.json') -Encoding ASCII
    foreach ($failAt in @(0,1,2)) {
        $caught = $false
        try {
            Invoke-VisionModelCatalogDeploy $source $plugin 'injected' -ProcessProbe $stopped -ValidateCatalog $valid -BeforeReplace {
                param($index) if ($index -eq $failAt) { throw "injected replace failure $index" }
            } | Out-Null
        } catch { $caught = $_.Exception.Message -like '*injected replace failure*' }
        Assert-True $caught 'Injected replacement failure must fail deployment.'
        $restored = @('net48','net7.0','net8.0') | ForEach-Object { Get-VisionCatalogFileManifest (Join-Path $plugin "$_/vision-models/fal") | ConvertTo-Json -Compress }
        Assert-True (($restored -join "`n") -ceq ($original -join "`n")) 'Rollback must restore all runtime catalogs.'
        Assert-True ((Get-VisionPayloadManifest $plugin) -ceq $before) 'Rollback must preserve every code payload hash.'
    }
    $rejected = $false
    try { Invoke-VisionModelCatalogDeploy $source $plugin 'injected' -ProcessProbe { 'Rhino' } -ValidateCatalog $valid | Out-Null } catch { $rejected = $_.Exception.Message -like '*Rhino*stopped*' }
    Assert-True $rejected 'Running Rhino must prevent config deployment.'
    $unexpectedCode = Join-Path $plugin 'net48/vision-models/fal/keep.dll'
    'code in catalog directory' | Set-Content -LiteralPath $unexpectedCode -Encoding ASCII
    $rejected = $false
    try { Invoke-VisionModelCatalogDeploy $source $plugin 'injected' -ProcessProbe $stopped -ValidateCatalog $valid | Out-Null } catch { $rejected = $_.Exception.Message -like '*non-JSON*' }
    Assert-True ($rejected -and (Test-Path -LiteralPath $unexpectedCode)) 'Config-only deployment must reject non-JSON installed catalog files before replacement.'
    Remove-Item -LiteralPath $unexpectedCode

    $hashProofFailed = $false
    try {
        Invoke-VisionModelCatalogDeploy $source $plugin 'injected' -ProcessProbe $stopped -ValidateCatalog $valid -BeforeReplace {
            param($index) if ($index -eq 1) { 'external change' | Set-Content -LiteralPath (Join-Path $plugin 'panel.js') -Encoding ASCII }
        } | Out-Null
    } catch { $hashProofFailed = $_.Exception.Message -like '*Code payload hash proof failed*' }
    Assert-True $hashProofFailed 'Any code hash drift must fail deployment proof.'
    $restored = @('net48','net7.0','net8.0') | ForEach-Object { Get-VisionCatalogFileManifest (Join-Path $plugin "$_/vision-models/fal") | ConvertTo-Json -Compress }
    Assert-True (($restored -join "`n") -ceq ($original -join "`n")) 'Code hash proof failure must roll back every catalog.'
    # The copier cannot repair concurrent external edits to unrelated code.
    'ui' | Set-Content -LiteralPath (Join-Path $plugin 'panel.js') -Encoding ASCII
    $rejected = $false
    try { Assert-VisionContainedPath (Join-Path $temp 'RookNative-escape') $plugin | Out-Null } catch { $rejected = $true }
    Assert-True $rejected 'A sibling with a common prefix is outside the plugin root.'

    # A junction must be rejected before traversal or removal; junction creation needs no elevation.
    $outside = Join-Path $temp 'outside'
    New-Item -ItemType Directory -Path $outside | Out-Null
    'untouched' | Set-Content (Join-Path $outside 'sentinel') -Encoding ASCII
    $link = Join-Path $plugin 'net7.0/vision-models/link'
    New-Item -ItemType Junction -Path $link -Target $outside | Out-Null
    try {
        $rejected = $false
        try { Invoke-VisionModelCatalogDeploy $source $plugin 'injected' -ProcessProbe $stopped -ValidateCatalog $valid | Out-Null } catch { $rejected = $_.Exception.Message -like '*reparse*' }
        Assert-True $rejected 'Reparse descendants must be rejected before transaction operations.'
        Assert-True ((Get-Content (Join-Path $outside 'sentinel')) -ceq 'untouched') 'Junction target must remain untouched.'
    } finally { [IO.Directory]::Delete($link) }
    # An empty catalog is deployable, including installations with no prior catalogs.
    foreach ($runtime in @('net48','net7.0','net8.0')) { Remove-VisionSafeDirectory (Join-Path $plugin "$runtime/vision-models/fal") $plugin }
    $caught = $false
    try { Invoke-VisionModelCatalogDeploy $source $plugin 'injected' -ProcessProbe $stopped -ValidateCatalog $valid -BeforeReplace { param($index) if ($index -eq 2) { throw 'new installation failure' } } | Out-Null } catch { $caught = $_.Exception.Message -like '*new installation failure*' }
    Assert-True $caught 'Failure in a first catalog deployment must propagate.'
    foreach ($runtime in @('net48','net7.0','net8.0')) { Assert-True (-not (Test-Path -LiteralPath (Join-Path $plugin "$runtime/vision-models/fal"))) 'Rollback must restore absent original catalogs as absent.' }
    Remove-Item -LiteralPath (Join-Path $source 'nested/future.json')
    Invoke-VisionModelCatalogDeploy $source $plugin 'injected' -ProcessProbe $stopped -ValidateCatalog $valid | Out-Null
    foreach ($runtime in @('net48','net7.0','net8.0')) {
        Assert-True (@(Get-VisionCatalogFileManifest (Join-Path $plugin "$runtime/vision-models/fal")).Count -eq 1) 'Empty pre-acceptance catalog must be a valid package.'
    }
    Assert-True (@(Get-ChildItem -LiteralPath $plugin -Recurse -Force | Where-Object Name -Match '^fal\.(stage|backup)-').Count -eq 0) 'Transactions must remove staging and backup directories after success or restored failure.'
    if ($QualificationPath) {
        $exe = (Resolve-Path -LiteralPath $QualificationPath).ProviderPath
        $report = Join-Path $temp 'qualification.json'
        & $exe validate-catalog --root $source --report $report | Out-Host
        Assert-True ($LASTEXITCODE -eq 0 -and (Get-Content $report -Raw | ConvertFrom-Json).success) 'Production compiler must admit the empty catalog through the CLI.'
        '{"schema_version":1,"definitions":["missing.json"]}' | Set-Content (Join-Path $source 'catalog.json') -Encoding ASCII
        $invalidCatalogExit = $false
        try { Invoke-VisionCatalogValidation $source $exe } catch { $invalidCatalogExit = $true }
        Assert-True $invalidCatalogExit 'Real validator exit/report must reject missing manifest references.'
        $doc = Get-Content (Join-Path $repo 'docs/vision/fal-model-definition-v1.md') -Raw
        $image = [regex]::Matches($doc, '(?s)```json\s*(.*?)\s*```') | ForEach-Object { $_.Groups[1].Value } | Where-Object { $_ -match '"definition_id":"synthetic-image"' } | Select-Object -First 1
        Assert-True (-not [string]::IsNullOrWhiteSpace($image)) 'Synthetic documentation fixture must exist.'
        $image | Set-Content (Join-Path $source 'image.json') -Encoding ASCII
        '{"schema_version":1,"definitions":["image.json"]}' | Set-Content (Join-Path $source 'catalog.json') -Encoding ASCII
        & $exe validate-catalog --root $source --report $report | Out-Host
        Assert-True ($LASTEXITCODE -eq 0) 'CLI must compile a complete synthetic definition with production semantics.'
        $qualified = Get-Content $report -Raw | ConvertFrom-Json
        Assert-True ($qualified.definitions.Count -eq 1 -and $qualified.definitions[0].definition_hash.Length -eq 64 -and $qualified.files.Count -eq 2) 'CLI must record canonical identities and packaged JSON hashes.'
        foreach ($reserved in @('fal-ai/flux/schnell','nano-banana-2')) {
            $image.Replace('"model_id":"synthetic/image"', ('"model_id":"' + $reserved + '"')) | Set-Content (Join-Path $source 'image.json') -Encoding ASCII
            # Capture native stderr without PowerShell converting it to a terminating error.
            $previous = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
            try { & $exe validate-catalog --root $source --report $report 2>&1 | ForEach-Object { $_.ToString() } | Out-Host; $exitCode = $LASTEXITCODE } finally { $ErrorActionPreference = $previous }
            $diagnostic = Get-Content $report -Raw | ConvertFrom-Json
            Assert-True ($exitCode -ne 0 -and -not $diagnostic.success -and @($diagnostic.diagnostics | Where-Object pointer -EQ '/model_id').Count -eq 1) 'CLI must reserve real legacy registration IDs and aliases.'
        }
    }
    Write-Host 'Catalog deployment tests passed: generic JSON, invalid admission, three-runtime rollback, code hashes, process/reparse/containment guards, empty catalog.'
} finally {
    # Verify the exact temporary target and reject reparse descendants before cleanup.
    if (Get-Command Remove-VisionSafeDirectory -ErrorAction SilentlyContinue) {
        Remove-VisionSafeDirectory $temp ([IO.Path]::GetTempPath())
    }
}
