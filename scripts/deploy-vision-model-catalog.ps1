param(
    [string]$CatalogRoot,
    [string]$PluginRoot,
    [string]$ValidatorPath
)

$ErrorActionPreference = 'Stop'

function Assert-VisionContainedPath {
    param([string]$Path, [string]$Boundary)
    $full = [IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
    $root = [IO.Path]::GetFullPath($Boundary).TrimEnd('\', '/')
    if (-not $full.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Catalog target escapes selected root: $full (root $root)"
    }
    Assert-VisionNoReparsePath $full
    return $full
}

function Assert-VisionNoReparsePath {
    param([string]$Path)
    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        $item = Get-Item -LiteralPath $current -Force -ErrorAction SilentlyContinue
        if ($null -ne $item -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Catalog paths cannot contain reparse points: $current"
        }
        $current = [IO.Path]::GetDirectoryName($current)
    }
}

function Get-VisionTreeFiles {
    param([string]$Root)
    Assert-VisionNoReparsePath $Root
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) { throw "Directory missing: $Root" }
    # Walk explicitly: inspect each entry BEFORE descending, including hidden files.
    foreach ($entry in Get-ChildItem -LiteralPath $Root -Force) {
        Assert-VisionNoReparsePath $entry.FullName
        if ($entry.PSIsContainer) { Get-VisionTreeFiles $entry.FullName }
        else { $entry }
    }
}

function Get-VisionCatalogFileManifest {
    param([string]$Root)
    $full = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
    @(Get-VisionTreeFiles $full | Where-Object Extension -EQ '.json' | Sort-Object FullName | ForEach-Object {
        [ordered]@{
            path = $_.FullName.Substring($full.Length + 1).Replace('\', '/')
            sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToUpperInvariant()
        }
    })
}

function Get-VisionPayloadManifest {
    param([string]$PluginRoot, [string[]]$TransactionDirectories = @())
    $root = [IO.Path]::GetFullPath($PluginRoot).TrimEnd('\', '/')
    $catalogs = @('net48','net7.0','net8.0') | ForEach-Object { Join-Path $root "$_/vision-models/fal" }
    $rows = @(Get-VisionTreeFiles $root | Sort-Object FullName | ForEach-Object {
        $file = $_; $skip = $false
        foreach ($dir in $TransactionDirectories) {
            if ($file.FullName.StartsWith($dir.TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { $skip = $true; break }
        }
        if ($file.Extension -ieq '.json') {
            foreach ($dir in $catalogs) {
                if ($file.FullName.StartsWith($dir + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { $skip = $true; break }
            }
        }
        if (-not $skip) {
            [ordered]@{ path = $file.FullName.Substring($root.Length + 1).Replace('\','/'); sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToUpperInvariant() }
        }
    })
    # Canonical text compares the complete unrelated file set as well as every hash.
    ConvertTo-Json -InputObject $rows -Depth 4 -Compress
}

function Remove-VisionSafeDirectory {
    param([string]$Path, [string]$Boundary)
    $full = Assert-VisionContainedPath $Path $Boundary
    if (Test-Path -LiteralPath $full) {
        @(Get-VisionTreeFiles $full) | Out-Null
        Remove-Item -LiteralPath $full -Recurse -Force
    }
}

function Move-VisionSafeDirectory {
    param([string]$Source, [string]$Destination, [string]$Boundary)
    $from = Assert-VisionContainedPath $Source $Boundary
    $to = Assert-VisionContainedPath $Destination $Boundary
    @(Get-VisionTreeFiles $from) | Out-Null
    if (Test-Path -LiteralPath $to) { throw "Move destination already exists: $to" }
    Move-Item -LiteralPath $from -Destination $to
}

function Copy-VisionCatalogJson {
    param([string]$Source, [string]$Destination, [string]$Boundary)
    $sourceRoot = [IO.Path]::GetFullPath($Source).TrimEnd('\','/')
    $dest = Assert-VisionContainedPath $Destination $Boundary
    $files = @(Get-VisionTreeFiles $sourceRoot | Where-Object Extension -EQ '.json')
    if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot 'catalog.json') -PathType Leaf)) { throw "Catalog manifest missing: $sourceRoot" }
    New-Item -ItemType Directory -Path $dest -Force | Out-Null
    foreach ($file in $files) {
        $target = Assert-VisionContainedPath (Join-Path $dest $file.FullName.Substring($sourceRoot.Length + 1)) $dest
        New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $target -Force
    }
}

function Invoke-VisionCatalogValidation {
    param([string]$CatalogRoot, [string]$ValidatorPath)
    $validator = (Resolve-Path -LiteralPath $ValidatorPath -ErrorAction Stop).ProviderPath
    if (-not (Test-Path -LiteralPath $validator -PathType Leaf)) { throw 'Qualification executable missing.' }
    Assert-VisionNoReparsePath $validator
    $report = Join-Path ([IO.Path]::GetTempPath()) ('rook-catalog-validation-' + [Guid]::NewGuid().ToString('N') + '.json')
    try {
        & $validator validate-catalog --root $CatalogRoot --report $report | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "Catalog semantic validation failed: $CatalogRoot (exit $LASTEXITCODE)" }
        $result = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
        if ($result.success -ne $true -or [IO.Path]::GetFullPath([string]$result.root) -ine [IO.Path]::GetFullPath($CatalogRoot)) { throw 'Catalog qualification report did not admit the selected root.' }
    } finally {
        if (Test-Path -LiteralPath $report) { Remove-Item -LiteralPath $report -Force }
    }
}

function Invoke-VisionModelCatalogDeploy {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string]$CatalogRoot,
        [Parameter(Mandatory=$true)][string]$PluginRoot,
        [Parameter(Mandatory=$true)][string]$ValidatorPath,
        [scriptblock]$ProcessProbe = { @(Get-Process -Name Rhino -ErrorAction SilentlyContinue) },
        [scriptblock]$ValidateCatalog = { param($root,$validator) Invoke-VisionCatalogValidation $root $validator },
        [scriptblock]$BeforeReplace = { param($index) }
    )
    $catalog = (Resolve-Path -LiteralPath $CatalogRoot).ProviderPath.TrimEnd('\','/')
    $plugin = (Resolve-Path -LiteralPath $PluginRoot).ProviderPath.TrimEnd('\','/')
    Assert-VisionNoReparsePath $catalog
    Assert-VisionNoReparsePath $plugin
    if ($catalog -ieq $plugin -or $catalog.StartsWith($plugin + '\', [StringComparison]::OrdinalIgnoreCase) -or $plugin.StartsWith($catalog + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Catalog source and plugin roots must not overlap.' }
    if (@(& $ProcessProbe).Count -ne 0) { throw 'Rhino must be stopped before catalog deployment.' }
    # No installed mutation until complete source admission and path/payload preflight.
    & $ValidateCatalog $catalog $ValidatorPath | Out-Null
    $sourceFiles = @(Get-VisionCatalogFileManifest $catalog)
    $sourceManifest = ConvertTo-Json -InputObject $sourceFiles -Depth 4 -Compress
    $before = Get-VisionPayloadManifest $plugin
    $id = [Guid]::NewGuid().ToString('N')
    $entries = @('net48','net7.0','net8.0') | ForEach-Object {
        $runtime = Assert-VisionContainedPath (Join-Path $plugin $_) $plugin
        if (-not (Test-Path -LiteralPath $runtime -PathType Container)) { throw "Installed runtime missing: $runtime" }
        $parent = Assert-VisionContainedPath (Join-Path $runtime 'vision-models') $plugin
        $target = Assert-VisionContainedPath (Join-Path $parent 'fal') $plugin
        if (Test-Path -LiteralPath $target) {
            if (@(Get-VisionTreeFiles $target | Where-Object Extension -NE '.json').Count -ne 0) { throw "Installed catalog contains non-JSON files: $target" }
        }
        [pscustomobject]@{ Runtime = $_; Target = $target; Stage = (Join-Path $parent "fal.stage-$id"); Backup = (Join-Path $parent "fal.backup-$id"); HadTarget = (Test-Path -LiteralPath $target); BackedUp = $false; Replaced = $false; Parent = $parent; HadParent = (Test-Path -LiteralPath $parent) }
    }
    $transactions = @($entries | ForEach-Object { $_.Stage; $_.Backup })
    $committed = $false
    try {
        foreach ($entry in $entries) {
            Copy-VisionCatalogJson $catalog $entry.Stage $plugin
            & $ValidateCatalog $entry.Stage $ValidatorPath | Out-Null
            $staged = ConvertTo-Json -InputObject @(Get-VisionCatalogFileManifest $entry.Stage) -Depth 4 -Compress
            if ($sourceManifest -cne $staged) { throw 'Staged catalog hash parity failed.' }
        }
        if (@(& $ProcessProbe).Count -ne 0) { throw 'Rhino must remain stopped before catalog replacement.' }
        for ($i = 0; $i -lt $entries.Count; $i++) {
            $entry = $entries[$i]
            if ($entry.HadTarget) { Move-VisionSafeDirectory $entry.Target $entry.Backup $plugin; $entry.BackedUp = $true }
            & $BeforeReplace $i | Out-Null
            Move-VisionSafeDirectory $entry.Stage $entry.Target $plugin
            $entry.Replaced = $true
        }
        foreach ($entry in $entries) {
            $installed = ConvertTo-Json -InputObject @(Get-VisionCatalogFileManifest $entry.Target) -Depth 4 -Compress
            if ($sourceManifest -cne $installed) { throw 'Installed catalog hash parity failed.' }
        }
        if ($before -cne (Get-VisionPayloadManifest $plugin $transactions)) { throw 'Code payload hash proof failed: unrelated installed bytes changed.' }
        $committed = $true
    } catch {
        $failure = $_
        $rollbackErrors = @()
        foreach ($entry in $entries) {
            try {
                if ($entry.Replaced) { Remove-VisionSafeDirectory $entry.Target $plugin }
                if ($entry.BackedUp) { Move-VisionSafeDirectory $entry.Backup $entry.Target $plugin; $entry.BackedUp = $false }
            } catch { $rollbackErrors += $_.Exception.Message }
        }
        if ($rollbackErrors.Count) { throw "Catalog rollback failed; preserve backups for recovery: $($rollbackErrors -join '; '). Original error: $failure" }
        throw $failure
    } finally {
        foreach ($entry in $entries) {
            Remove-VisionSafeDirectory $entry.Stage $plugin
            # Never discard a backup after a failed restoration.
            if ($committed) { Remove-VisionSafeDirectory $entry.Backup $plugin }
            if (-not $entry.HadParent -and (Test-Path -LiteralPath $entry.Parent) -and @(Get-ChildItem -LiteralPath $entry.Parent -Force).Count -eq 0) { Remove-VisionSafeDirectory $entry.Parent $plugin }
        }
    }
    $after = Get-VisionPayloadManifest $plugin
    if ($before -cne $after) { throw 'Code payload hash proof failed after transaction cleanup.' }
    [pscustomobject]@{ RestartRequired = $true; CodeHashesUnchanged = $true; CodeManifestBefore = $before; CodeManifestAfter = $after; CatalogFiles = $sourceFiles; Runtimes = @($entries.Runtime) }
}

if ($MyInvocation.InvocationName -ne '.') {
    if (-not $CatalogRoot -or -not $PluginRoot -or -not $ValidatorPath) { throw 'CatalogRoot, PluginRoot and ValidatorPath are required.' }
    Invoke-VisionModelCatalogDeploy -CatalogRoot $CatalogRoot -PluginRoot $PluginRoot -ValidatorPath $ValidatorPath
    Write-Host 'Catalog deployed to net48/net7.0/net8.0. Restart Rhino to load it; all other payload hashes are unchanged.'
}
