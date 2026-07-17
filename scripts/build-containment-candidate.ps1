param(
    [Parameter(Mandatory = $true)][string]$RookRoot,
    [Parameter(Mandatory = $true)][string]$ExpectedBranch,
    [Parameter(Mandatory = $true)][string]$ExpectedRookSha,
    [Parameter(Mandatory = $true)][string]$ChirpRoot,
    [Parameter(Mandatory = $true)][string]$ExpectedChirpSha,
    [Parameter(Mandatory = $true)][string]$ArtifactDirectory,
    [Parameter(Mandatory = $true)][string]$GitPath,
    [Parameter(Mandatory = $true)][string]$PowerShellPath,
    [Parameter(Mandatory = $true)][string]$CmdPath,
    [Parameter(Mandatory = $true)][string]$Msys2Bash,
    [Parameter(Mandatory = $true)][string]$VcvarsallPath,
    [Parameter(Mandatory = $true)][string]$MsbuildPath,
    [Parameter(Mandatory = $true)][string]$DotnetPath,
    [Parameter(Mandatory = $true)][string]$RhinoSystemDir,
    [Parameter(Mandatory = $true)][string]$RevitInstallDir,
    [Parameter(Mandatory = $true)][string]$VcRedistRoot,
    [Parameter(Mandatory = $true)][string]$OcctRoot,
    [Parameter(Mandatory = $true)][string]$OcctRuntimeRoot,
    [Parameter(Mandatory = $true)][string]$IsccPath
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$OcctImportLibraries = @(
    'TKernel.lib','TKMath.lib','TKG2d.lib','TKG3d.lib','TKGeomBase.lib','TKGeomAlgo.lib','TKBRep.lib',
    'TKTopAlgo.lib','TKPrim.lib','TKBO.lib','TKBool.lib','TKShHealing.lib','TKMesh.lib'
)
$VcRedistFiles = @(
    'Microsoft.VC143.CRT\concrt140.dll','Microsoft.VC143.CRT\msvcp140.dll',
    'Microsoft.VC143.CRT\vcruntime140.dll','Microsoft.VC143.CRT\vcruntime140_1.dll',
    'Microsoft.VC143.MFC\mfc140.dll','Microsoft.VC143.MFC\mfc140u.dll'
)
$RookTrackedBuildOutputPaths = @(
    'third_party/ffmpeg/ffmpeg-provenance.json',
    'third_party/ffmpeg/ffmpeg.exe'
)
$RhinoManagedReferenceFiles = @('netcore\RhinoCommon.dll','netcore\Rhino.UI.dll','Eto.dll','RhinoCommon.dll')
$RevitReferenceFiles = @('RevitAPI.dll','RevitAPIUI.dll')
$NativeEnvironmentAllowlist = @(
    'SystemRoot','windir','TEMP','TMP','ComSpec','PATHEXT','PROCESSOR_ARCHITECTURE',
    'ProgramFiles','ProgramFiles(x86)','ProgramData','SystemDrive','NUMBER_OF_PROCESSORS','OS','PATH'
)
$NativeEnvironmentScrubNames = @(
    'CL','_CL_','LINK','_LINK_','INCLUDE','LIB','LIBPATH',
    'VCTargetsPath','VCTargetsPath10','VCTargetsPath11','VCTargetsPath12','VCTargetsPath14','VCTargetsPath15','VCTargetsPath16','VCTargetsPath17',
    'MSBUILD_EXE_PATH','MSBuildExtensionsPath','MSBuildExtensionsPath32','MSBuildExtensionsPath64','MSBuildSDKsPath','MSBuildToolsPath','MSBuildToolsPath32','MSBuildToolsPath64','MSBuildToolsRoot','MSBuildUserExtensionsPath','MSBuildProjectExtensionsPath','MSBUILDLEGACYEXTENSIONSPATH',
    'DirectoryBuildPropsPath','DirectoryBuildTargetsPath','AlternateCommonProps','CustomBeforeMicrosoftCommonProps','CustomAfterMicrosoftCommonProps','CustomBeforeMicrosoftCommonTargets','CustomAfterMicrosoftCommonTargets','CustomBeforeDirectoryBuildProps','CustomAfterDirectoryBuildProps','CustomBeforeDirectoryBuildTargets','CustomAfterDirectoryBuildTargets','ForceImportAfterCppDefaultProps','ForceImportBeforeCppProps','ForceImportAfterCppProps','ForceImportBeforeCppTargets','ForceImportAfterCppTargets','BaseIntermediateOutputPath','ProjectExtensionsPathForSpecifiedProject','ProjectToOverrideProjectExtensionsPath','NuGetPropsFile','NuGetRestoreTargets','AdditionalVCTargetsPath','DisableInstalledVCTargetsUse','DisableInstalledVCTargetsDefaultsUse','VcpkgInstalledVCTargets','VcpkgManifestDirectory','ImportBeforeCppProps','ImportAfterCppProps','ImportBeforeCppTargets','ImportAfterCppTargets','ImportDirectoryBuildProps','ImportDirectoryBuildTargets','ImportProjectExtensionProps','ImportProjectExtensionTargets','ImportUserLocationsByWildcardBeforeMicrosoftCommonProps','ImportUserLocationsByWildcardAfterMicrosoftCommonProps','ImportUserLocationsByWildcardBeforeMicrosoftCommonTargets','ImportUserLocationsByWildcardAfterMicrosoftCommonTargets'
)
$DirectNativeHookNames = @(
    'CL','_CL_','LINK','_LINK_',
    'DirectoryBuildPropsPath','DirectoryBuildTargetsPath','AlternateCommonProps','CustomBeforeMicrosoftCommonProps','CustomAfterMicrosoftCommonProps','CustomBeforeMicrosoftCommonTargets','CustomAfterMicrosoftCommonTargets','CustomBeforeDirectoryBuildProps','CustomAfterDirectoryBuildProps','CustomBeforeDirectoryBuildTargets','CustomAfterDirectoryBuildTargets','ForceImportAfterCppDefaultProps','ForceImportBeforeCppProps','ForceImportAfterCppProps','ForceImportBeforeCppTargets','ForceImportAfterCppTargets','BaseIntermediateOutputPath','ProjectExtensionsPathForSpecifiedProject','ProjectToOverrideProjectExtensionsPath','NuGetPropsFile','NuGetRestoreTargets','AdditionalVCTargetsPath','DisableInstalledVCTargetsUse','DisableInstalledVCTargetsDefaultsUse','VcpkgInstalledVCTargets','VcpkgManifestDirectory','ImportBeforeCppProps','ImportAfterCppProps','ImportBeforeCppTargets','ImportAfterCppTargets','ImportDirectoryBuildProps','ImportDirectoryBuildTargets','ImportProjectExtensionProps','ImportProjectExtensionTargets','ImportUserLocationsByWildcardBeforeMicrosoftCommonProps','ImportUserLocationsByWildcardAfterMicrosoftCommonProps','ImportUserLocationsByWildcardBeforeMicrosoftCommonTargets','ImportUserLocationsByWildcardAfterMicrosoftCommonTargets'
)
$PostVcvarsForbiddenNames = @($DirectNativeHookNames) + @(
    'MSBuildUserExtensionsPath','MSBuildProjectExtensionsPath','MSBUILDLEGACYEXTENSIONSPATH'
)
$MsbuildImportDisableArguments = @(
    '/p:ImportDirectoryBuildProps=false','/p:ImportDirectoryBuildTargets=false',
    '/p:ImportProjectExtensionProps=false','/p:ImportProjectExtensionTargets=false',
    '/p:ImportUserLocationsByWildcardBeforeMicrosoftCommonProps=false',
    '/p:ImportUserLocationsByWildcardAfterMicrosoftCommonProps=false',
    '/p:ImportUserLocationsByWildcardBeforeMicrosoftCommonTargets=false',
    '/p:ImportUserLocationsByWildcardAfterMicrosoftCommonTargets=false'
)
$RequiredContainmentFixtureSize = 2708
$RequiredContainmentFixtureSha256 = '2def4c0009b3b41de681fe23880f741189c0119820260a35a48f048d2b8830df'
$RequiredPrivatePythonVersion = '3.11.9'
$NativeToolsetVersion = '14.44.35207'
$NativeVcvarsSelector = '14.44'
$StreamDrainTimeoutMilliseconds = 10000
$ProcessTerminationTimeoutMilliseconds = 10000
$RhinoSdkRegistryKey = 'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\McNeel\Rhinoceros\SDK\8.0'
$script:CommandRecords = New-Object System.Collections.ArrayList
$script:CommandOrdinal = 0
$script:LogsDirectory = $null
$script:CanonicalCmdPath = $null

function Assert-Condition {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Get-OrdinalSortedStrings {
    param([AllowEmptyCollection()][string[]]$Values, [switch]$Unique)
    [string[]]$sorted = @($Values)
    [System.Array]::Sort($sorted, [StringComparer]::Ordinal)
    if (-not $Unique) { return $sorted }
    $result = New-Object System.Collections.Generic.List[string]
    foreach ($value in $sorted) {
        if ($result.Count -eq 0 -or -not [string]::Equals($result[$result.Count - 1],$value,[StringComparison]::Ordinal)) { $result.Add($value) }
    }
    return $result.ToArray()
}

function Write-Utf8NoBom {
    param([string]$Path, [string]$Text)
    [System.IO.File]::WriteAllText($Path, $Text, [System.Text.UTF8Encoding]::new($false))
}

function Get-LowerSha256 {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-BytesSha256 {
    param([byte[]]$Bytes)
    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    try { $hash = $algorithm.ComputeHash($Bytes) } finally { $algorithm.Dispose() }
    return ([System.BitConverter]::ToString($hash) -replace '-', '').ToLowerInvariant()
}

function Get-StringSha256 {
    param([string]$Text)
    return Get-BytesSha256 -Bytes ([System.Text.UTF8Encoding]::new($false).GetBytes($Text))
}

function Test-ReparsePoint {
    param([string]$Path)
    $item = Get-Item -LiteralPath $Path -Force
    return (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0)
}

function Assert-NoReparsePathComponents {
    param([string]$Path, [string]$Label)
    $item = Get-Item -LiteralPath $Path -Force
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "$Label must not contain a reparse-point path component: $($item.FullName)"
    }
    if (-not $item.PSIsContainer) { $item = $item.Directory }
    while ($null -ne $item) {
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "$Label must not contain a reparse-point path component: $($item.FullName)"
        }
        $item = $item.Parent
    }
}

function Resolve-RequiredDirectory {
    param([string]$Path, [string]$Label, [switch]$AllowReparsePoint)
    if (-not [System.IO.Path]::IsPathRooted($Path)) { throw "$Label must be an absolute path: $Path" }
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { throw "$Label is missing: $Path" }
    $resolved = (Resolve-Path -LiteralPath $Path).Path.TrimEnd('\')
    if (-not $AllowReparsePoint) { Assert-NoReparsePathComponents -Path $resolved -Label $Label }
    return $resolved
}

function Resolve-RequiredFile {
    param([string]$Path, [string]$Label)
    if (-not [System.IO.Path]::IsPathRooted($Path)) { throw "$Label must be an absolute path: $Path" }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "$Label is missing: $Path" }
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    Assert-NoReparsePathComponents -Path $resolved -Label $Label
    return $resolved
}

function Test-PathWithin {
    param([string]$Path, [string]$Root)
    $candidate = [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
    $boundary = [System.IO.Path]::GetFullPath($Root).TrimEnd('\')
    return [string]::Equals($candidate, $boundary, [StringComparison]::OrdinalIgnoreCase) -or
        $candidate.StartsWith($boundary + '\', [StringComparison]::OrdinalIgnoreCase)
}

function Assert-DisjointPaths {
    param([string]$First, [string]$FirstLabel, [string]$Second, [string]$SecondLabel)
    if ((Test-PathWithin -Path $First -Root $Second) -or (Test-PathWithin -Path $Second -Root $First)) {
        throw "$FirstLabel overlaps ${SecondLabel}: $First / $Second"
    }
}

function Get-FileIdentity {
    param([string]$Path)
    $canonicalPath = Resolve-RequiredFile -Path $Path -Label 'File identity input'
    $item = Get-Item -LiteralPath $canonicalPath -Force
    $version = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($item.FullName)
    return [ordered]@{
        path = $item.FullName
        size = [long]$item.Length
        sha256 = Get-LowerSha256 -Path $item.FullName
        file_version = [string]$version.FileVersion
        product_version = [string]$version.ProductVersion
    }
}

function Assert-FileIdentityUnchanged {
    param([object]$Expected, [string]$Label)
    $current = Get-FileIdentity -Path ([string]$Expected.path)
    if (-not [string]::Equals([string]$current.path, [string]$Expected.path, [StringComparison]::OrdinalIgnoreCase) -or
        [long]$current.size -ne [long]$Expected.size -or
        -not [string]::Equals([string]$current.sha256, [string]$Expected.sha256, [StringComparison]::Ordinal) -or
        -not [string]::Equals([string]$current.file_version, [string]$Expected.file_version, [StringComparison]::Ordinal) -or
        -not [string]::Equals([string]$current.product_version, [string]$Expected.product_version, [StringComparison]::Ordinal)) {
        throw "$Label identity drift: $($Expected.path)"
    }
}

function ConvertTo-ProcessArgument {
    param([AllowNull()][AllowEmptyString()][string]$Value)
    if ($null -eq $Value -or $Value.Length -eq 0) { return '""' }
    if ($Value -notmatch '[\s"]') { return $Value }
    $escaped = $Value -replace '(\\*)"', '$1$1\"'
    $escaped = $escaped -replace '(\\+)$', '$1$1'
    return '"' + $escaped + '"'
}

function ConvertTo-CmdQuotedArgument {
    param([string]$Value)
    if ($Value -match '["\r\n%]') { throw "Value cannot be represented safely in a private cmd batch: $Value" }
    return '"' + $Value + '"'
}

function Wait-TaskBounded {
    param([System.Threading.Tasks.Task]$Task, [string]$Label, [int]$TimeoutMilliseconds)
    if (-not $Task.Wait($TimeoutMilliseconds)) { throw "$Label timed out after $TimeoutMilliseconds milliseconds" }
    return $Task.GetAwaiter().GetResult()
}

function ConvertTo-CanonicalJson {
    param([AllowNull()][object]$Value)
    if ($null -eq $Value) { return 'null' }
    if ($Value -is [bool]) { if ($Value) { return 'true' } else { return 'false' } }
    if ($Value -is [string] -or $Value -is [char]) { return (ConvertTo-Json -InputObject ([string]$Value) -Compress) }
    if ($Value -is [datetime]) { return (ConvertTo-Json -InputObject $Value.ToUniversalTime().ToString('o') -Compress) }
    if ($Value -is [System.Collections.IDictionary]) {
        [string[]]$keys = @($Value.Keys | ForEach-Object { [string]$_ })
        [System.Array]::Sort($keys, [StringComparer]::Ordinal)
        $parts = foreach ($key in $keys) {
            (ConvertTo-Json -InputObject $key -Compress) + ':' + (ConvertTo-CanonicalJson -Value $Value[$key])
        }
        return '{' + ($parts -join ',') + '}'
    }
    if ($Value -is [pscustomobject]) {
        $dictionary = [ordered]@{}
        foreach ($property in $Value.PSObject.Properties) { $dictionary[$property.Name] = $property.Value }
        return ConvertTo-CanonicalJson -Value $dictionary
    }
    if ($Value -is [System.Collections.IEnumerable]) {
        $items = foreach ($item in $Value) { ConvertTo-CanonicalJson -Value $item }
        return '[' + ($items -join ',') + ']'
    }
    if ($Value -is [byte] -or $Value -is [sbyte] -or $Value -is [int16] -or $Value -is [uint16] -or
        $Value -is [int32] -or $Value -is [uint32] -or $Value -is [int64] -or $Value -is [uint64] -or
        $Value -is [single] -or $Value -is [double] -or $Value -is [decimal]) {
        return ([System.Convert]::ToString($Value, [System.Globalization.CultureInfo]::InvariantCulture))
    }
    return (ConvertTo-Json -InputObject ([string]$Value) -Compress)
}

function Get-RelativePathText {
    param([string]$Root, [string]$Path)
    $canonicalRoot = [System.IO.Path]::GetFullPath($Root).TrimEnd('\')
    $canonicalPath = [System.IO.Path]::GetFullPath($Path)
    Assert-Condition -Condition (Test-PathWithin -Path $canonicalPath -Root $canonicalRoot) -Message "Path is outside inventory root: $canonicalPath"
    return $canonicalPath.Substring($canonicalRoot.Length).TrimStart('\').Replace('\','/')
}

function Get-TreeInventory {
    param([string]$Root, [switch]$ExcludeGit)
    if (-not (Test-Path -LiteralPath $Root)) { return @() }
    $rootItem = Get-Item -LiteralPath $Root -Force
    if (($rootItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Inventory tree must not contain a reparse point: $($rootItem.FullName)" }
    if (-not $rootItem.PSIsContainer) { throw "Inventory root must be a directory: $($rootItem.FullName)" }
    $resolvedRoot = Resolve-RequiredDirectory -Path $rootItem.FullName -Label 'Inventory root'
    $recordsByPath = [System.Collections.Generic.SortedDictionary[string,object]]::new([StringComparer]::Ordinal)
    $pendingDirectories = New-Object System.Collections.Generic.Stack[string]
    $pendingDirectories.Push($resolvedRoot)
    while ($pendingDirectories.Count -ne 0) {
        $directory = $pendingDirectories.Pop()
        foreach ($item in @(Get-ChildItem -LiteralPath $directory -Force)) {
            $relativePath = Get-RelativePathText -Root $resolvedRoot -Path $item.FullName
            if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Inventory tree must not contain a reparse point: $($item.FullName)" }
            if ($ExcludeGit -and $relativePath -match '(?i)(^|/)\.git(/|$)') { continue }
            if ($item.PSIsContainer) {
                $pendingDirectories.Push($item.FullName)
                continue
            }
            if (-not ($item -is [System.IO.FileInfo])) { throw "Inventory tree contains an unsupported filesystem object: $($item.FullName)" }
            $record = [ordered]@{
                relative_path = $relativePath
                size = [long]$item.Length
                sha256 = Get-LowerSha256 -Path $item.FullName
            }
            $recordsByPath.Add([string]$record.relative_path,$record)
        }
    }
    return @($recordsByPath.Values)
}

function New-InventoryProjection {
    param([object[]]$Files)
    $stable = @($Files)
    $canonical = ConvertTo-CanonicalJson -Value $stable
    return [ordered]@{ digest = Get-StringSha256 -Text $canonical; files = $stable }
}

function Get-SelectedFileProjection {
    param([string]$Root, [string[]]$RelativePaths, [string]$MissingLabel)
    $canonicalRoot = Resolve-RequiredDirectory -Path $Root -Label "$MissingLabel root"
    $records = foreach ($relative in @(Get-OrdinalSortedStrings -Values $RelativePaths)) {
        $normalizedRelative = $relative.Replace('/','\')
        if ([System.IO.Path]::IsPathRooted($normalizedRelative) -or @($normalizedRelative -split '\\' | Where-Object { $_ -eq '..' }).Count -ne 0) {
            throw "$MissingLabel contains an unsafe relative path: $relative"
        }
        $path = Join-Path $canonicalRoot $normalizedRelative
        $resolvedPath = Resolve-RequiredFile -Path $path -Label $MissingLabel
        if (-not (Test-PathWithin -Path $resolvedPath -Root $canonicalRoot)) { throw "$MissingLabel escaped its canonical root: $relative" }
        $item = Get-Item -LiteralPath $resolvedPath -Force
        [ordered]@{
            relative_path = $normalizedRelative.Replace('\','/')
            size = [long]$item.Length
            sha256 = Get-LowerSha256 -Path $item.FullName
        }
    }
    return New-InventoryProjection -Files @($records)
}

function Get-LivePluginProjection {
    param([string]$Path)
    $absolute = [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
    $exists = Test-Path -LiteralPath $absolute
    $files = @()
    if ($exists) {
        $item = Get-Item -LiteralPath $absolute -Force
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Live RookNative plug-in path must not be a reparse point: $absolute" }
        if (-not $item.PSIsContainer) { throw "Live RookNative plug-in path must be absent or a directory: $absolute" }
        $files = @(Get-TreeInventory -Root $absolute)
    }
    $projection = [ordered]@{ exists = [bool]$exists; path = $absolute; files = $files }
    return [ordered]@{ projection = $projection; sha256 = Get-StringSha256 -Text (ConvertTo-CanonicalJson -Value $projection) }
}

function New-CommandRecord {
    param(
        [string]$Name,
        [string]$Executable,
        [string[]]$Arguments,
        [string]$WorkingDirectory,
        [int]$ExitCode,
        [string]$LogPrefix
    )
    return [ordered]@{
        name = $Name
        executable = $Executable
        arguments = @($Arguments)
        working_directory = $WorkingDirectory
        exit_code = $ExitCode
        log_prefix = Get-RelativePathText -Root (Split-Path -Parent $script:LogsDirectory) -Path $LogPrefix
    }
}

function Invoke-External {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory,
        [System.Collections.Generic.Dictionary[string,string]]$Environment,
        [int]$TimeoutMilliseconds = 7200000,
        [switch]$UseExplicitCmdWrapper
    )
    $script:CommandOrdinal++
    $safeName = $Name -replace '[^A-Za-z0-9_.-]', '-'
    $logPrefix = Join-Path $script:LogsDirectory ('{0:D3}-{1}' -f $script:CommandOrdinal, $safeName)
    $stdoutPath = "$logPrefix.stdout.log"
    $stderrPath = "$logPrefix.stderr.log"
    Write-Utf8NoBom -Path $stdoutPath -Text ''
    Write-Utf8NoBom -Path $stderrPath -Text ''
    $actualFile = $FilePath
    $actualArguments = @($Arguments)
    if ($UseExplicitCmdWrapper) {
        Assert-Condition -Condition ($null -ne $script:CanonicalCmdPath) -Message 'Explicit CmdPath is not initialized.'
        $wrapperPath = "$logPrefix.wrapper.cmd"
        $line = 'call ' + (ConvertTo-CmdQuotedArgument -Value $FilePath)
        foreach ($argument in $Arguments) { $line += ' ' + (ConvertTo-CmdQuotedArgument -Value $argument) }
        Write-Utf8NoBom -Path $wrapperPath -Text ("@echo off`r`n$line`r`nexit /b %errorlevel%`r`n")
        $actualFile = $script:CanonicalCmdPath
        $actualArguments = @('/d','/c',$wrapperPath)
    }

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $actualFile
    $psi.Arguments = (@($actualArguments) | ForEach-Object { ConvertTo-ProcessArgument $_ }) -join ' '
    $psi.WorkingDirectory = $WorkingDirectory
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    if ($null -ne $Environment) {
        $psi.EnvironmentVariables.Clear()
        foreach ($entry in $Environment.GetEnumerator()) { $psi.EnvironmentVariables[$entry.Key] = $entry.Value }
    }

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    try {
        if (-not $process.Start()) { throw "Failed to start $Name via $actualFile" }
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutMilliseconds)) {
            try { $process.Kill() } catch {}
            try { [void]$process.WaitForExit($ProcessTerminationTimeoutMilliseconds) } catch {}
            Write-Utf8NoBom -Path $stderrPath -Text "$Name timed out; redirected output capture was abandoned within the bounded termination window.`n"
            throw "$Name timed out after $TimeoutMilliseconds milliseconds"
        }
        $stdout = Wait-TaskBounded -Task $stdoutTask -Label "$Name stdout drain" -TimeoutMilliseconds $StreamDrainTimeoutMilliseconds
        $stderr = Wait-TaskBounded -Task $stderrTask -Label "$Name stderr drain" -TimeoutMilliseconds $StreamDrainTimeoutMilliseconds
        $exitCode = $process.ExitCode
    } finally {
        $process.Dispose()
    }
    Write-Utf8NoBom -Path $stdoutPath -Text $stdout
    Write-Utf8NoBom -Path $stderrPath -Text $stderr
    $record = New-CommandRecord -Name $Name -Executable $FilePath -Arguments $Arguments -WorkingDirectory $WorkingDirectory -ExitCode $exitCode -LogPrefix $logPrefix
    [void]$script:CommandRecords.Add($record)
    if ($exitCode -ne 0) { throw "$Name failed with exit code $exitCode. See $stdoutPath and $stderrPath" }
    return [ordered]@{ stdout = $stdout; stderr = $stderr; exit_code = $exitCode }
}

function Invoke-ExternalBinaryOutput {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory,
        [string]$OutputPath,
        [int]$TimeoutMilliseconds = 120000
    )
    $script:CommandOrdinal++
    $safeName = $Name -replace '[^A-Za-z0-9_.-]', '-'
    $logPrefix = Join-Path $script:LogsDirectory ('{0:D3}-{1}' -f $script:CommandOrdinal, $safeName)
    $stdoutPath = "$logPrefix.stdout.log"
    $stderrPath = "$logPrefix.stderr.log"
    Write-Utf8NoBom -Path $stdoutPath -Text ''
    Write-Utf8NoBom -Path $stderrPath -Text ''
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.Arguments = (@($Arguments) | ForEach-Object { ConvertTo-ProcessArgument $_ }) -join ' '
    $psi.WorkingDirectory = $WorkingDirectory
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    $outputStream = [System.IO.File]::Open($OutputPath,[System.IO.FileMode]::CreateNew,[System.IO.FileAccess]::Write,[System.IO.FileShare]::None)
    try {
        if (-not $process.Start()) { throw "Failed to start $Name via $FilePath" }
        $copyTask = $process.StandardOutput.BaseStream.CopyToAsync($outputStream)
        $stderrTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutMilliseconds)) {
            try { $process.Kill() } catch {}
            try { [void]$process.WaitForExit($ProcessTerminationTimeoutMilliseconds) } catch {}
            Write-Utf8NoBom -Path $stderrPath -Text "$Name timed out; binary output capture was abandoned within the bounded termination window.`n"
            throw "$Name timed out after $TimeoutMilliseconds milliseconds"
        }
        [void](Wait-TaskBounded -Task $copyTask -Label "$Name binary stdout drain" -TimeoutMilliseconds $StreamDrainTimeoutMilliseconds)
        $stderr = Wait-TaskBounded -Task $stderrTask -Label "$Name stderr drain" -TimeoutMilliseconds $StreamDrainTimeoutMilliseconds
        $exitCode = $process.ExitCode
    } finally {
        $outputStream.Dispose()
        $process.Dispose()
    }
    Write-Utf8NoBom -Path $stdoutPath -Text ("Binary stdout captured to $OutputPath ($((Get-Item -LiteralPath $OutputPath).Length) bytes)`n")
    Write-Utf8NoBom -Path $stderrPath -Text $stderr
    $record = New-CommandRecord -Name $Name -Executable $FilePath -Arguments $Arguments -WorkingDirectory $WorkingDirectory -ExitCode $exitCode -LogPrefix $logPrefix
    [void]$script:CommandRecords.Add($record)
    if ($exitCode -ne 0) { throw "$Name failed with exit code $exitCode. See $stdoutPath and $stderrPath" }
}

function Invoke-ExactTool {
    param(
        [string]$Name,[string]$FilePath,[string[]]$Arguments,[string]$WorkingDirectory,
        [System.Collections.Generic.Dictionary[string,string]]$Environment,[int]$TimeoutMilliseconds = 7200000
    )
    $extension = [System.IO.Path]::GetExtension($FilePath)
    $needsCmd = [string]::Equals($extension,'.cmd',[StringComparison]::OrdinalIgnoreCase) -or [string]::Equals($extension,'.bat',[StringComparison]::OrdinalIgnoreCase)
    return Invoke-External -Name $Name -FilePath $FilePath -Arguments $Arguments -WorkingDirectory $WorkingDirectory -Environment $Environment -TimeoutMilliseconds $TimeoutMilliseconds -UseExplicitCmdWrapper:$needsCmd
}

function Invoke-GitText {
    param([string]$Name, [string]$Root, [string[]]$Arguments)
    $result = Invoke-External -Name $Name -FilePath $script:CanonicalGitPath -Arguments (@('-C',$Root) + $Arguments) -WorkingDirectory $Root -Environment $null -TimeoutMilliseconds 120000
    return ([string]$result.stdout).Trim()
}

function Get-GitSourceState {
    param([string]$Label, [string]$Root)
    $currentRoot = Resolve-RequiredDirectory -Path $Root -Label "$Label source root"
    if (-not [string]::Equals($currentRoot,$Root,[StringComparison]::OrdinalIgnoreCase)) { throw "$Label source root identity drift: $Root / $currentRoot" }
    $reportedRoot = Invoke-GitText -Name ("git-{0}-root" -f $Label.ToLowerInvariant()) -Root $Root -Arguments @('rev-parse','--show-toplevel')
    $canonicalReportedRoot = (Resolve-Path -LiteralPath $reportedRoot).Path.TrimEnd('\')
    if (-not [string]::Equals($canonicalReportedRoot, $Root, [StringComparison]::OrdinalIgnoreCase)) {
        throw "${Label}Root is not the Git top-level: $Root (reported $canonicalReportedRoot)"
    }
    $head = Invoke-GitText -Name ("git-{0}-head" -f $Label.ToLowerInvariant()) -Root $Root -Arguments @('rev-parse','HEAD')
    $branch = Invoke-GitText -Name ("git-{0}-branch" -f $Label.ToLowerInvariant()) -Root $Root -Arguments @('branch','--show-current')
    $status = Invoke-GitText -Name ("git-{0}-status" -f $Label.ToLowerInvariant()) -Root $Root -Arguments @('status','--porcelain=v1','--untracked-files=all')
    return [ordered]@{ root = $Root; head = $head; branch = $branch; clean = [string]::IsNullOrEmpty($status); status = $status }
}

function Assert-OriginalSourceState {
    param([string]$Label, [object]$Expected)
    $current = Get-GitSourceState -Label $Label -Root ([string]$Expected.root)
    if (-not [string]::Equals([string]$current.head, [string]$Expected.head, [StringComparison]::Ordinal) -or
        -not [string]::Equals([string]$current.branch, [string]$Expected.branch, [StringComparison]::Ordinal) -or
        -not [bool]$current.clean) {
        throw "$Label source changed during candidate construction"
    }
}

function Assert-StagedTrackedSourcesUnchanged {
    param([string]$Label, [string]$Root, [string]$ExpectedSha, [string[]]$AllowedChangedPaths = @())
    $currentRoot = Resolve-RequiredDirectory -Path $Root -Label "$Label tracked source root"
    if (-not [string]::Equals($currentRoot,$Root,[StringComparison]::OrdinalIgnoreCase)) { throw "$Label tracked source root identity drift: $Root / $currentRoot" }
    $head = Invoke-GitText -Name ("git-{0}-tracked-head" -f $Label.ToLowerInvariant()) -Root $Root -Arguments @('rev-parse','HEAD')
    $branch = Invoke-GitText -Name ("git-{0}-tracked-branch" -f $Label.ToLowerInvariant()) -Root $Root -Arguments @('branch','--show-current')
    $changedText = Invoke-GitText -Name ("git-{0}-tracked-diff" -f $Label.ToLowerInvariant()) -Root $Root -Arguments @('diff','--name-only','HEAD','--')
    $changedPaths = if ([string]::IsNullOrEmpty($changedText)) { @() } else { @($changedText -split "`r?`n" | ForEach-Object { $_.Replace('\','/') }) }
    $allowed = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($path in $AllowedChangedPaths) { [void]$allowed.Add($path.Replace('\','/')) }
    $unexpectedPaths = @($changedPaths | Where-Object { -not $allowed.Contains($_) })
    if (-not [string]::Equals($head,$ExpectedSha,[StringComparison]::Ordinal) -or
        -not [string]::IsNullOrEmpty($branch) -or
        $unexpectedPaths.Count -ne 0) {
        throw "$Label tracked source changed during candidate construction"
    }
}

function Get-VersionFromFile {
    param([string]$Path, [string]$Pattern, [string]$Label)
    $text = Get-Content -LiteralPath $Path -Raw
    $match = [regex]::Match($text, $Pattern)
    if (-not $match.Success -or [string]::IsNullOrWhiteSpace($match.Groups[1].Value)) { throw "Could not read $Label version from $Path" }
    return $match.Groups[1].Value
}

function Get-RegistryRhinoSdkInstallPath {
    $registry = Get-ItemProperty -LiteralPath $RhinoSdkRegistryKey -Name InstallPath -ErrorAction Stop
    return Resolve-RequiredDirectory -Path ([string]$registry.InstallPath) -Label 'Registry-resolved Rhino SDK InstallPath'
}

function Assert-RhinoSdkAuthorityUnchanged {
    param([string]$ExpectedInstallPath, [object]$ExpectedPropertySheetIdentity)
    $currentInstallPath = Get-RegistryRhinoSdkInstallPath
    if (-not [string]::Equals($currentInstallPath,$ExpectedInstallPath,[StringComparison]::OrdinalIgnoreCase)) {
        throw "Registry-resolved Rhino SDK authority changed: expected $ExpectedInstallPath, got $currentInstallPath"
    }
    $currentPropertySheetPath = Resolve-RequiredFile -Path (Join-Path $currentInstallPath 'PropertySheets\Rhino.Cpp.PlugIn.props') -Label 'Registry-resolved Rhino SDK property sheet'
    if (-not [string]::Equals($currentPropertySheetPath,[string]$ExpectedPropertySheetIdentity.path,[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Registry-resolved Rhino SDK property-sheet path changed'
    }
    Assert-FileIdentityUnchanged -Expected $ExpectedPropertySheetIdentity -Label 'Rhino SDK property sheet'
}

function Get-EnvironmentProjection {
    param([System.Collections.Generic.Dictionary[string,string]]$Environment)
    $names = [string[]]@($Environment.Keys)
    [System.Array]::Sort($names, [StringComparer]::Ordinal)
    return @($names | ForEach-Object { [ordered]@{ name = $_; value = $Environment[$_] } })
}

function Read-EnvironmentFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Environment capture is missing: $Path" }
    $map = [System.Collections.Generic.Dictionary[string,string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        $equals = $line.IndexOf('=')
        if ($equals -le 0) { throw "Malformed environment capture line: $line" }
        $name = $line.Substring(0,$equals)
        $value = $line.Substring($equals + 1)
        if ($map.ContainsKey($name)) { throw "Duplicate environment capture name: $name" }
        $map.Add($name,$value)
    }
    return $map
}

function Assert-EnvironmentKeySet {
    param([System.Collections.Generic.Dictionary[string,string]]$Environment, [string[]]$ExpectedNames, [string]$Label)
    $actual = @(Get-OrdinalSortedStrings -Values @($Environment.Keys))
    $expected = @(Get-OrdinalSortedStrings -Values $ExpectedNames)
    $delta = @(Compare-Object $expected $actual)
    if ($delta.Count -ne 0) { throw "$Label key set mismatch: $($delta | Out-String)" }
}

function Get-CanonicalExistingPathSegment {
    param([string]$Path, [string]$Label)
    $trimmed = $Path.Trim().Trim('"').TrimEnd('\')
    if (-not $trimmed) { throw "$Label contains an empty path segment" }
    if (-not [System.IO.Path]::IsPathRooted($trimmed)) { throw "$Label contains a relative path segment: $trimmed" }
    if (-not (Test-Path -LiteralPath $trimmed)) { throw "$Label contains a missing path segment: $trimmed" }
    if (Test-Path -LiteralPath $trimmed -PathType Container) { return Resolve-RequiredDirectory -Path $trimmed -Label $Label }
    return Resolve-RequiredFile -Path $trimmed -Label $Label
}

function Assert-CapturedNativeEnvironment {
    param(
        [System.Collections.Generic.Dictionary[string,string]]$Captured,
        [string]$VsRoot,
        [string]$SystemRoot,
        [string]$ProgramFilesRoot,
        [string]$ProgramFilesX86Root,
        [string[]]$HostileValues
    )
    foreach ($name in $PostVcvarsForbiddenNames) {
        if ($Captured.ContainsKey($name) -and -not [string]::IsNullOrWhiteSpace($Captured[$name])) {
            throw "Captured native environment retained forbidden authority $name"
        }
    }
    foreach ($entry in $Captured.GetEnumerator()) {
        foreach ($hostile in $HostileValues) {
            if ($hostile.Length -ge 8 -and $entry.Value.IndexOf($hostile, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
                throw "Captured native environment retained hostile value in $($entry.Key)"
            }
        }
    }
    if (-not $Captured.ContainsKey('VCToolsInstallDir')) { throw 'Captured native environment is missing VCToolsInstallDir' }
    $vcTools = Get-CanonicalExistingPathSegment -Path $Captured['VCToolsInstallDir'] -Label 'VCToolsInstallDir'
    if (-not [string]::Equals((Split-Path -Leaf $vcTools), $NativeToolsetVersion, [StringComparison]::Ordinal)) {
        throw "Captured VCToolsInstallDir does not select $NativeToolsetVersion`: $vcTools"
    }
    Assert-Condition -Condition (Test-PathWithin -Path $vcTools -Root $VsRoot) -Message "Captured VCToolsInstallDir is outside the explicit VS installation: $vcTools"

    $sdkRoots = New-Object System.Collections.ArrayList
    foreach ($name in @('WindowsSdkDir','UniversalCRTSdkDir','UCRTContentRoot','NETFXSDKDir')) {
        if ($Captured.ContainsKey($name) -and -not [string]::IsNullOrWhiteSpace($Captured[$name])) {
            $sdk = Get-CanonicalExistingPathSegment -Path $Captured[$name] -Label $name
            $trustedSdkParent = (Test-PathWithin -Path $sdk -Root $ProgramFilesRoot) -or (Test-PathWithin -Path $sdk -Root $ProgramFilesX86Root) -or (Test-PathWithin -Path $sdk -Root $SystemRoot)
            Assert-Condition -Condition $trustedSdkParent -Message "$name is outside the validated Windows SDK/UCRT installation roots: $sdk"
            [void]$sdkRoots.Add($sdk)
        }
    }
    Assert-Condition -Condition ($sdkRoots.Count -ge 1) -Message 'Captured native environment did not identify a Windows SDK/UCRT root.'
    $auxiliaryRoots = New-Object System.Collections.ArrayList
    foreach ($relative in @('Microsoft SDKs\Windows\v10.0A\bin\NETFX 4.8 Tools\x64','HTML Help Workshop')) {
        $candidate = Join-Path $ProgramFilesX86Root $relative
        if (Test-Path -LiteralPath $candidate -PathType Container) {
            [void]$auxiliaryRoots.Add((Resolve-RequiredDirectory -Path $candidate -Label "Trusted vcvars auxiliary root $relative"))
        }
    }
    $allowedRoots = @($VsRoot,$SystemRoot) + @($sdkRoots) + @($auxiliaryRoots)
    $listPathNames = @('INCLUDE','LIB','LIBPATH','PATH')
    foreach ($name in $listPathNames) {
        if (-not $Captured.ContainsKey($name) -or [string]::IsNullOrWhiteSpace($Captured[$name])) { throw "Captured native environment is missing $name" }
        foreach ($segment in ($Captured[$name] -split ';' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })) {
            $canonical = Get-CanonicalExistingPathSegment -Path $segment -Label $name
            $allowed = $false
            foreach ($root in $allowedRoots) { if (Test-PathWithin -Path $canonical -Root $root) { $allowed = $true; break } }
            Assert-Condition -Condition $allowed -Message "$name contains a path outside the explicit VS/SDK/SystemRoot authority: $canonical"
        }
    }
    $singlePathPatterns = @(
        '^VCTargetsPath(?:10|11|12|14|15|16|17)?$',
        '^MSBuild(?:ExtensionsPath(?:32|64)?|SDKsPath|ToolsPath(?:32|64)?|ToolsRoot)$',
        '^MSBUILD_EXE_PATH$'
    )
    foreach ($entry in $Captured.GetEnumerator()) {
        $isPath = $false
        foreach ($pattern in $singlePathPatterns) { if ($entry.Key -match $pattern) { $isPath = $true; break } }
        if (-not $isPath -or [string]::IsNullOrWhiteSpace($entry.Value)) { continue }
        $canonical = Get-CanonicalExistingPathSegment -Path $entry.Value -Label $entry.Key
        $allowed = $false
        foreach ($root in $allowedRoots) { if (Test-PathWithin -Path $canonical -Root $root) { $allowed = $true; break } }
        Assert-Condition -Condition $allowed -Message "$($entry.Key) is outside the explicit VS/SDK/SystemRoot authority: $canonical"
    }
    $projectionNames = New-Object System.Collections.ArrayList
    foreach ($name in @('VCToolsInstallDir','WindowsSdkDir','UniversalCRTSdkDir','UCRTContentRoot','NETFXSDKDir','INCLUDE','LIB','LIBPATH','PATH')) {
        if ($Captured.ContainsKey($name)) { [void]$projectionNames.Add($name) }
    }
    foreach ($entry in $Captured.GetEnumerator()) {
        foreach ($pattern in $singlePathPatterns) {
            if ($entry.Key -match $pattern) { [void]$projectionNames.Add($entry.Key); break }
        }
    }
    $projection = [ordered]@{}
    foreach ($name in @(Get-OrdinalSortedStrings -Values @($projectionNames) -Unique)) { $projection[$name] = $Captured[$name] }
    return $projection
}

function Get-CanonicalPotentialDirectoryPath {
    param([string]$Path, [string]$Label)
    if (-not [System.IO.Path]::IsPathRooted($Path)) { throw "$Label must be an absolute path: $Path" }
    $full = [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
    if (Test-Path -LiteralPath $full -PathType Leaf) { throw "$Label is a file: $full" }
    if (Test-Path -LiteralPath $full -PathType Container) { return Resolve-RequiredDirectory -Path $full -Label $Label }
    $ancestor = $full
    while (-not (Test-Path -LiteralPath $ancestor -PathType Container)) {
        $parent = Split-Path -Parent $ancestor
        if (-not $parent -or [string]::Equals($parent,$ancestor,[StringComparison]::OrdinalIgnoreCase)) { throw "$Label has no existing parent: $full" }
        $ancestor = $parent
    }
    $resolvedAncestor = Resolve-RequiredDirectory -Path $ancestor -Label "$Label ancestor"
    $suffix = $full.Substring($ancestor.Length).TrimStart('\')
    if ($suffix) { return Join-Path $resolvedAncestor $suffix }
    return $resolvedAncestor
}

function Get-CanonicalArtifactPath {
    param([string]$Path)
    if (-not [System.IO.Path]::IsPathRooted($Path)) { throw "ArtifactDirectory must be an absolute path: $Path" }
    $full = [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
    if (Test-Path -LiteralPath $full -PathType Leaf) { throw "ArtifactDirectory is a file: $full" }
    if (Test-Path -LiteralPath $full -PathType Container) {
        if (Test-ReparsePoint -Path $full) { throw "ArtifactDirectory must not be a reparse point: $full" }
        if (@(Get-ChildItem -LiteralPath $full -Force).Count -ne 0) { throw "ArtifactDirectory must be empty: $full" }
    }
    $ancestor = $full
    while (-not (Test-Path -LiteralPath $ancestor -PathType Container)) {
        $parent = Split-Path -Parent $ancestor
        if (-not $parent -or [string]::Equals($parent,$ancestor,[StringComparison]::OrdinalIgnoreCase)) { throw "ArtifactDirectory has no existing parent: $full" }
        $ancestor = $parent
    }
    $resolvedAncestor = (Resolve-Path -LiteralPath $ancestor).Path.TrimEnd('\')
    Assert-NoReparsePathComponents -Path $resolvedAncestor -Label 'ArtifactDirectory ancestor'
    if (-not [string]::Equals($ancestor,$resolvedAncestor,[StringComparison]::OrdinalIgnoreCase)) {
        $suffix = $full.Substring($ancestor.Length).TrimStart('\')
        $full = Join-Path $resolvedAncestor $suffix
    }
    return $full
}

function Get-InstallerOcctRuntimeDlls {
    param([string]$InstallerPath)
    $text = Get-Content -LiteralPath $InstallerPath -Raw
    $matches = [regex]::Matches($text, '(?im)Source:\s*"\{#OcctRuntimeRoot\}\\(?<name>[^"\\]+\.dll)"')
    $names = @(Get-OrdinalSortedStrings -Values @($matches | ForEach-Object { $_.Groups['name'].Value }) -Unique)
    if ($names.Count -eq 0) { throw "Installer has no OCCT runtime DLL inputs: $InstallerPath" }
    foreach ($name in $names) {
        if ($name -match '[/\\]' -or $name -match '(^|\.)\.($|\.)') { throw "Installer OCCT runtime input is not a leaf DLL name: $name" }
    }
    return $names
}

function Assert-ProjectionUnchanged {
    param([object]$Expected, [object]$Current, [string]$Label)
    if (-not [string]::Equals([string]$Expected.digest, [string]$Current.digest, [StringComparison]::Ordinal)) {
        throw "$Label identity drift"
    }
}

function Assert-ContainmentWheelFixture {
    param([string]$WheelhouseRoot, [string]$Version)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $wheels = @(Get-ChildItem -LiteralPath $WheelhouseRoot -Filter "rook-$Version-*.whl" -File)
    if ($wheels.Count -ne 1) { throw "Expected exactly one Rook wheel for $Version; found $($wheels.Count)" }
    $archive = [System.IO.Compression.ZipFile]::OpenRead($wheels[0].FullName)
    try {
        $entries = @($archive.Entries | Where-Object { $_.FullName -ceq 'rook/resources/containment_empty.ghx' })
        if ($entries.Count -ne 1) { throw 'Built Rook wheel must contain exactly one rook/resources/containment_empty.ghx entry' }
        $stream = $entries[0].Open()
        $memory = New-Object System.IO.MemoryStream
        try { $stream.CopyTo($memory); $bytes = $memory.ToArray() } finally { $stream.Dispose(); $memory.Dispose() }
    } finally { $archive.Dispose() }
    if ($bytes.Length -ne $RequiredContainmentFixtureSize) { throw "Wheel containment_empty.ghx size mismatch: $($bytes.Length)" }
    if (-not [string]::Equals((Get-BytesSha256 -Bytes $bytes),$RequiredContainmentFixtureSha256,[StringComparison]::Ordinal)) { throw 'Wheel containment_empty.ghx SHA-256 mismatch' }
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) { throw 'Wheel containment_empty.ghx must not contain a UTF-8 BOM' }
    if (@($bytes | Where-Object { $_ -eq 13 }).Count -ne 0) { throw 'Wheel containment_empty.ghx must use LF endings' }
    if ($bytes[-1] -ne 10 -or ($bytes.Length -gt 1 -and $bytes[-2] -eq 10)) { throw 'Wheel containment_empty.ghx must have exactly one final LF' }
    [void][System.Text.UTF8Encoding]::new($false,$true).GetString($bytes)
}

function Get-NativeVsRoot {
    param([string]$VcvarsPath)
    $current = Split-Path -Parent $VcvarsPath
    for ($i = 0; $i -lt 3; $i++) { $current = Split-Path -Parent $current }
    return Resolve-RequiredDirectory -Path $current -Label 'Visual Studio installation root'
}

function New-PrivateNativeEnvironment {
    param([string]$ArtifactRoot, [string]$CanonicalCmd)
    if (-not [Environment]::Is64BitProcess) { throw 'Candidate construction requires a 64-bit Windows PowerShell process' }
    $cmdItem = Get-Item -LiteralPath $CanonicalCmd
    if (-not [string]::Equals($cmdItem.Name,'cmd.exe',[StringComparison]::OrdinalIgnoreCase)) { throw "CmdPath must name cmd.exe: $CanonicalCmd" }
    $system32 = Split-Path -Parent $CanonicalCmd
    if (-not [string]::Equals((Split-Path -Leaf $system32),'System32',[StringComparison]::OrdinalIgnoreCase)) { throw "CmdPath must be the canonical System32 cmd.exe: $CanonicalCmd" }
    $systemRoot = Resolve-RequiredDirectory -Path (Split-Path -Parent $system32) -Label 'SystemRoot'
    $programFiles = Resolve-RequiredDirectory -Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::ProgramFiles)) -Label 'ProgramFiles'
    $programFilesX86 = Resolve-RequiredDirectory -Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::ProgramFilesX86)) -Label 'ProgramFiles(x86)'
    $programData = Resolve-RequiredDirectory -Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::CommonApplicationData)) -Label 'ProgramData'
    $nativeRoot = Join-Path $ArtifactRoot '_native_environment'
    $temp = Join-Path $nativeRoot 'TEMP'
    $tmp = Join-Path $nativeRoot 'TMP'
    foreach ($path in @($nativeRoot,$temp,$tmp)) {
        if (Test-Path -LiteralPath $path) { throw "Fresh native environment path already exists: $path" }
        New-Item -ItemType Directory -Path $path | Out-Null
        if (Test-ReparsePoint -Path $path) { throw "Native environment path must not be a reparse point: $path" }
    }
    $environment = [System.Collections.Generic.Dictionary[string,string]]::new([StringComparer]::OrdinalIgnoreCase)
    $environment.Add('SystemRoot',$systemRoot)
    $environment.Add('windir',$systemRoot)
    $environment.Add('TEMP',$temp)
    $environment.Add('TMP',$tmp)
    $environment.Add('ComSpec',$CanonicalCmd)
    $environment.Add('PATHEXT','.COM;.EXE;.BAT;.CMD')
    $environment.Add('PROCESSOR_ARCHITECTURE','AMD64')
    $environment.Add('ProgramFiles',$programFiles)
    $environment.Add('ProgramFiles(x86)',$programFilesX86)
    $environment.Add('ProgramData',$programData)
    $environment.Add('SystemDrive',[System.IO.Path]::GetPathRoot($systemRoot).TrimEnd('\'))
    $environment.Add('NUMBER_OF_PROCESSORS',[Environment]::ProcessorCount.ToString([Globalization.CultureInfo]::InvariantCulture))
    $environment.Add('OS','Windows_NT')
    $environment.Add('PATH',"$systemRoot\System32;$systemRoot;$systemRoot\System32\Wbem")
    foreach ($name in $NativeEnvironmentScrubNames) { [void]$environment.Remove($name) }
    Assert-EnvironmentKeySet -Environment $environment -ExpectedNames $NativeEnvironmentAllowlist -Label 'Private pre-vcvars environment'
    return [ordered]@{
        environment = $environment
        system_root = $systemRoot
        program_files = $programFiles
        program_files_x86 = $programFilesX86
        program_data = $programData
    }
}

$buildStartedUtc = [DateTime]::UtcNow.ToString('o')
if ($ExpectedRookSha -cnotmatch '^[0-9a-f]{40}$') { throw "ExpectedRookSha must be exactly 40 lowercase hex characters: $ExpectedRookSha" }
if ($ExpectedChirpSha -cnotmatch '^[0-9a-f]{40}$') { throw "ExpectedChirpSha must be exactly 40 lowercase hex characters: $ExpectedChirpSha" }
if ([string]::IsNullOrWhiteSpace($ExpectedBranch)) { throw 'ExpectedBranch must not be empty' }

$canonicalRookRoot = Resolve-RequiredDirectory -Path $RookRoot -Label 'RookRoot'
$canonicalChirpRoot = Resolve-RequiredDirectory -Path $ChirpRoot -Label 'ChirpRoot'
$canonicalArtifact = Get-CanonicalArtifactPath -Path $ArtifactDirectory
$script:CanonicalGitPath = Resolve-RequiredFile -Path $GitPath -Label 'GitPath'
$canonicalPowerShellPath = Resolve-RequiredFile -Path $PowerShellPath -Label 'PowerShellPath'
$script:CanonicalCmdPath = Resolve-RequiredFile -Path $CmdPath -Label 'CmdPath'
$canonicalMsys2Bash = Resolve-RequiredFile -Path $Msys2Bash -Label 'Msys2Bash'
$canonicalVcvarsallPath = Resolve-RequiredFile -Path $VcvarsallPath -Label 'VcvarsallPath'
$canonicalMsbuildPath = Resolve-RequiredFile -Path $MsbuildPath -Label 'MsbuildPath'
$canonicalDotnetPath = Resolve-RequiredFile -Path $DotnetPath -Label 'DotnetPath'
$canonicalIsccPath = Resolve-RequiredFile -Path $IsccPath -Label 'IsccPath'
$canonicalRhinoSystemDir = Resolve-RequiredDirectory -Path $RhinoSystemDir -Label 'RhinoSystemDir'
$canonicalRevitInstallDir = Resolve-RequiredDirectory -Path $RevitInstallDir -Label 'RevitInstallDir'
$canonicalVcRedistRoot = Resolve-RequiredDirectory -Path $VcRedistRoot -Label 'VcRedistRoot'
$canonicalOcctRoot = Resolve-RequiredDirectory -Path $OcctRoot -Label 'OcctRoot'
$canonicalOcctRuntimeRoot = Resolve-RequiredDirectory -Path $OcctRuntimeRoot -Label 'OcctRuntimeRoot'
$rhinoSdkInstallPath = Get-RegistryRhinoSdkInstallPath
$ambientEnvironment = [Environment]::GetEnvironmentVariables()
if (-not $ambientEnvironment.Contains('APPDATA') -or [string]::IsNullOrWhiteSpace([string]$ambientEnvironment['APPDATA'])) { throw 'APPDATA is missing from the builder environment' }
$canonicalAppData = Resolve-RequiredDirectory -Path ([string]$ambientEnvironment['APPDATA']) -Label 'APPDATA'
$livePluginPath = Get-CanonicalPotentialDirectoryPath -Path (Join-Path $canonicalAppData 'McNeel\Rhinoceros\8.0\Plug-ins\RookNative') -Label 'Live RookNative plug-in directory'
$livePluginBefore = Get-LivePluginProjection -Path $livePluginPath

Assert-DisjointPaths -First $canonicalRookRoot -FirstLabel 'RookRoot' -Second $canonicalChirpRoot -SecondLabel 'ChirpRoot'
if ((Test-PathWithin -Path $canonicalArtifact -Root $canonicalRookRoot) -or (Test-PathWithin -Path $canonicalRookRoot -Root $canonicalArtifact) -or
    (Test-PathWithin -Path $canonicalArtifact -Root $canonicalChirpRoot) -or (Test-PathWithin -Path $canonicalChirpRoot -Root $canonicalArtifact)) {
    throw "ArtifactDirectory overlaps a source root: $canonicalArtifact"
}
if ((Test-PathWithin -Path $canonicalArtifact -Root $livePluginPath) -or (Test-PathWithin -Path $livePluginPath -Root $canonicalArtifact)) {
    throw "ArtifactDirectory overlaps the live RookNative plug-in directory: $canonicalArtifact / $livePluginPath"
}
foreach ($externalRoot in @($canonicalRhinoSystemDir,$canonicalRevitInstallDir,$canonicalVcRedistRoot,$canonicalOcctRoot,$rhinoSdkInstallPath)) {
    if ((Test-PathWithin -Path $canonicalArtifact -Root $externalRoot) -or (Test-PathWithin -Path $externalRoot -Root $canonicalArtifact)) {
        throw "ArtifactDirectory overlaps an external input root: $canonicalArtifact / $externalRoot"
    }
}
$disjointInputRoots = @(
    [pscustomobject]@{ label = 'RookRoot'; path = $canonicalRookRoot },
    [pscustomobject]@{ label = 'ChirpRoot'; path = $canonicalChirpRoot },
    [pscustomobject]@{ label = 'RhinoSystemDir'; path = $canonicalRhinoSystemDir },
    [pscustomobject]@{ label = 'RevitInstallDir'; path = $canonicalRevitInstallDir },
    [pscustomobject]@{ label = 'VcRedistRoot'; path = $canonicalVcRedistRoot },
    [pscustomobject]@{ label = 'OcctRoot'; path = $canonicalOcctRoot },
    [pscustomobject]@{ label = 'RhinoSdkInstallPath'; path = $rhinoSdkInstallPath }
)
for ($firstIndex = 0; $firstIndex -lt $disjointInputRoots.Count; $firstIndex++) {
    for ($secondIndex = $firstIndex + 1; $secondIndex -lt $disjointInputRoots.Count; $secondIndex++) {
        $firstRoot = $disjointInputRoots[$firstIndex]
        $secondRoot = $disjointInputRoots[$secondIndex]
        if ((Test-PathWithin -Path $firstRoot.path -Root $secondRoot.path) -or (Test-PathWithin -Path $secondRoot.path -Root $firstRoot.path)) {
            throw "External input roots overlap: $($firstRoot.label)=$($firstRoot.path) / $($secondRoot.label)=$($secondRoot.path)"
        }
    }
}
$rhinoSdkPropertySheetPath = Resolve-RequiredFile -Path (Join-Path $rhinoSdkInstallPath 'PropertySheets\Rhino.Cpp.PlugIn.props') -Label 'Registry-resolved Rhino SDK property sheet'
$rhinoSdkPropertySheetIdentity = Get-FileIdentity -Path $rhinoSdkPropertySheetPath
$requiredOcctRuntimeRoot = [System.IO.Path]::GetFullPath((Join-Path $canonicalOcctRoot 'win64\vc14\bin')).TrimEnd('\')
if (-not [string]::Equals($canonicalOcctRuntimeRoot,$requiredOcctRuntimeRoot,[StringComparison]::OrdinalIgnoreCase)) {
    throw "OcctRuntimeRoot must equal OcctRoot\win64\vc14\bin: expected $requiredOcctRuntimeRoot, got $canonicalOcctRuntimeRoot"
}
$toolPaths = @($script:CanonicalGitPath,$canonicalPowerShellPath,$script:CanonicalCmdPath,$canonicalMsys2Bash,$canonicalVcvarsallPath,$canonicalMsbuildPath,$canonicalDotnetPath,$canonicalIsccPath)
if (@($toolPaths | Sort-Object -Unique).Count -ne $toolPaths.Count) { throw 'External executable paths must be distinct and unambiguous' }

if (-not (Test-Path -LiteralPath $canonicalArtifact -PathType Container)) { New-Item -ItemType Directory -Path $canonicalArtifact -Force | Out-Null }
$canonicalArtifact = (Resolve-Path -LiteralPath $canonicalArtifact).Path.TrimEnd('\')
Assert-NoReparsePathComponents -Path $canonicalArtifact -Label 'ArtifactDirectory'
$script:LogsDirectory = Join-Path $canonicalArtifact 'logs'
New-Item -ItemType Directory -Path $script:LogsDirectory | Out-Null

$toolIdentities = [ordered]@{
    GitPath = Get-FileIdentity -Path $script:CanonicalGitPath
    PowerShellPath = Get-FileIdentity -Path $canonicalPowerShellPath
    CmdPath = Get-FileIdentity -Path $script:CanonicalCmdPath
    Msys2Bash = Get-FileIdentity -Path $canonicalMsys2Bash
    VcvarsallPath = Get-FileIdentity -Path $canonicalVcvarsallPath
    MsbuildPath = Get-FileIdentity -Path $canonicalMsbuildPath
    DotnetPath = Get-FileIdentity -Path $canonicalDotnetPath
    IsccPath = Get-FileIdentity -Path $canonicalIsccPath
}

$rookInitialState = Get-GitSourceState -Label 'Rook' -Root $canonicalRookRoot
if (-not [string]::Equals([string]$rookInitialState.branch,$ExpectedBranch,[StringComparison]::Ordinal)) { throw "Rook branch mismatch: expected $ExpectedBranch, got $($rookInitialState.branch)" }
if (-not [string]::Equals([string]$rookInitialState.head,$ExpectedRookSha,[StringComparison]::Ordinal)) { throw "Rook HEAD mismatch: expected $ExpectedRookSha, got $($rookInitialState.head)" }
if (-not [bool]$rookInitialState.clean) { throw "Rook source is not clean: $($rookInitialState.status)" }
$chirpInitialState = Get-GitSourceState -Label 'Chirp' -Root $canonicalChirpRoot
if (-not [string]::Equals([string]$chirpInitialState.head,$ExpectedChirpSha,[StringComparison]::Ordinal)) { throw "Chirp HEAD mismatch: expected $ExpectedChirpSha, got $($chirpInitialState.head)" }
if (-not [bool]$chirpInitialState.clean) { throw "Chirp source is not clean: $($chirpInitialState.status)" }

$originalInstallerPath = Resolve-RequiredFile -Path (Join-Path $canonicalRookRoot 'installer\RookSetup.iss') -Label 'Reviewed installer source'
$installerOcctDlls = @(Get-InstallerOcctRuntimeDlls -InstallerPath $originalInstallerPath)
$occtBuildRelativePaths = @('inc\Standard.hxx') + @($OcctImportLibraries | ForEach-Object { "win64\vc14\lib\$_" })
if (-not (Test-Path -LiteralPath (Join-Path $canonicalOcctRoot 'inc\Standard.hxx') -PathType Leaf)) { throw "OCCT header is missing: $(Join-Path $canonicalOcctRoot 'inc\Standard.hxx')" }
$initialOcctBuildProjection = Get-SelectedFileProjection -Root $canonicalOcctRoot -RelativePaths $occtBuildRelativePaths -MissingLabel 'OCCT import input'
$initialOcctRuntimeProjection = Get-SelectedFileProjection -Root $canonicalOcctRuntimeRoot -RelativePaths $installerOcctDlls -MissingLabel 'OCCT runtime DLL'
$vcRedistProjection = Get-SelectedFileProjection -Root $canonicalVcRedistRoot -RelativePaths $VcRedistFiles -MissingLabel 'VC redistributable input'
$rhinoManagedProjection = Get-SelectedFileProjection -Root $canonicalRhinoSystemDir -RelativePaths $RhinoManagedReferenceFiles -MissingLabel 'Rhino managed reference'
$revitProjection = Get-SelectedFileProjection -Root $canonicalRevitInstallDir -RelativePaths $RevitReferenceFiles -MissingLabel 'Revit reference'

$nativeProjectSource = Resolve-RequiredFile -Path (Join-Path $canonicalRookRoot 'src\RookNative\RookNative.vcxproj') -Label 'Native project source'
$nativeProjectText = Get-Content -LiteralPath $nativeProjectSource -Raw
Assert-Condition -Condition $nativeProjectText.Contains("GetRegistryValueFromView('HKEY_LOCAL_MACHINE\SOFTWARE\McNeel\Rhinoceros\SDK\8.0', 'InstallPath', '', RegistryView.Registry64)") -Message 'Native project does not use the pinned registry-resolved Rhino SDK property sheet'
$hostileValuesList = New-Object System.Collections.ArrayList
foreach ($name in (@($NativeEnvironmentScrubNames) + @('PATH'))) {
    if ($ambientEnvironment.Contains($name)) {
        $value = [string]$ambientEnvironment[$name]
        if (-not [string]::IsNullOrWhiteSpace($value) -and -not $hostileValuesList.Contains($value)) { [void]$hostileValuesList.Add($value) }
    }
}
$hostileValues = @($hostileValuesList | ForEach-Object { [string]$_ })

$runId = [guid]::NewGuid().ToString('N')
$inertRhinoPluginDir = Join-Path $canonicalArtifact ("_no_rhino_deploy_$runId")
Assert-Condition -Condition (-not (Test-Path -LiteralPath $inertRhinoPluginDir)) -Message "inert RhinoPluginDir already exists: $inertRhinoPluginDir"

$stageRoot = Join-Path $canonicalArtifact 'stage'
$stagedRook = Join-Path $stageRoot 'Rook'
$stagedChirp = Join-Path $stageRoot 'Chirp'
New-Item -ItemType Directory -Path $stageRoot | Out-Null
Invoke-External -Name 'clone-rook' -FilePath $script:CanonicalGitPath -Arguments @('-c','core.autocrlf=false','clone','--local','--no-hardlinks','--no-checkout','--',$canonicalRookRoot,$stagedRook) -WorkingDirectory $canonicalArtifact -Environment $null -TimeoutMilliseconds 120000 | Out-Null
Invoke-GitText -Name 'configure-rook-stage-eol' -Root $stagedRook -Arguments @('config','core.autocrlf','false') | Out-Null
Invoke-GitText -Name 'configure-rook-lfs-process' -Root $stagedRook -Arguments @('config','filter.lfs.process','') | Out-Null
Invoke-GitText -Name 'configure-rook-lfs-smudge' -Root $stagedRook -Arguments @('config','filter.lfs.smudge','') | Out-Null
Invoke-GitText -Name 'configure-rook-lfs-clean' -Root $stagedRook -Arguments @('config','filter.lfs.clean','') | Out-Null
Invoke-GitText -Name 'configure-rook-lfs-required' -Root $stagedRook -Arguments @('config','filter.lfs.required','false') | Out-Null
Invoke-GitText -Name 'checkout-rook' -Root $stagedRook -Arguments @('-c','filter.lfs.process=','-c','filter.lfs.smudge=','-c','filter.lfs.required=false','checkout','--detach',$ExpectedRookSha) | Out-Null
Invoke-GitText -Name 'remove-rook-origin' -Root $stagedRook -Arguments @('remote','remove','origin') | Out-Null
Invoke-External -Name 'clone-chirp' -FilePath $script:CanonicalGitPath -Arguments @('-c','core.autocrlf=false','clone','--local','--no-hardlinks','--no-checkout','--',$canonicalChirpRoot,$stagedChirp) -WorkingDirectory $canonicalArtifact -Environment $null -TimeoutMilliseconds 120000 | Out-Null
Invoke-GitText -Name 'configure-chirp-stage-eol' -Root $stagedChirp -Arguments @('config','core.autocrlf','false') | Out-Null
Invoke-GitText -Name 'configure-chirp-lfs-process' -Root $stagedChirp -Arguments @('config','filter.lfs.process','') | Out-Null
Invoke-GitText -Name 'configure-chirp-lfs-smudge' -Root $stagedChirp -Arguments @('config','filter.lfs.smudge','') | Out-Null
Invoke-GitText -Name 'configure-chirp-lfs-clean' -Root $stagedChirp -Arguments @('config','filter.lfs.clean','') | Out-Null
Invoke-GitText -Name 'configure-chirp-lfs-required' -Root $stagedChirp -Arguments @('config','filter.lfs.required','false') | Out-Null
Invoke-GitText -Name 'checkout-chirp' -Root $stagedChirp -Arguments @('-c','filter.lfs.process=','-c','filter.lfs.smudge=','-c','filter.lfs.required=false','checkout','--detach',$ExpectedChirpSha) | Out-Null
Invoke-GitText -Name 'remove-chirp-origin' -Root $stagedChirp -Arguments @('remote','remove','origin') | Out-Null

$stagedRookState = Get-GitSourceState -Label 'StagedRook' -Root $stagedRook
$stagedChirpState = Get-GitSourceState -Label 'StagedChirp' -Root $stagedChirp
Assert-Condition -Condition ([string]::Equals([string]$stagedRookState.head,$ExpectedRookSha,[StringComparison]::Ordinal) -and [string]::IsNullOrEmpty([string]$stagedRookState.branch) -and [bool]$stagedRookState.clean) -Message 'Staged Rook clone is not clean, detached, and exact'
Assert-Condition -Condition ([string]::Equals([string]$stagedChirpState.head,$ExpectedChirpSha,[StringComparison]::Ordinal) -and [string]::IsNullOrEmpty([string]$stagedChirpState.branch) -and [bool]$stagedChirpState.clean) -Message 'Staged Chirp clone is not clean, detached, and exact'

$sourceEvidenceRoot = Join-Path $canonicalArtifact 'source-evidence'
New-Item -ItemType Directory -Path $sourceEvidenceRoot | Out-Null
$rookArchivePath = Join-Path $sourceEvidenceRoot 'Rook.tar'
$chirpArchivePath = Join-Path $sourceEvidenceRoot 'Chirp.tar'
Invoke-GitText -Name 'archive-rook-source' -Root $canonicalRookRoot -Arguments @('archive','--format=tar',"--output=$rookArchivePath",$ExpectedRookSha) | Out-Null
Invoke-GitText -Name 'archive-chirp-source' -Root $canonicalChirpRoot -Arguments @('archive','--format=tar',"--output=$chirpArchivePath",$ExpectedChirpSha) | Out-Null
$reviewedInstallerPath = Join-Path $sourceEvidenceRoot 'RookSetup.reviewed.iss'
Invoke-ExternalBinaryOutput -Name 'extract-reviewed-installer' -FilePath $script:CanonicalGitPath -Arguments @('-C',$canonicalRookRoot,'cat-file','blob',"${ExpectedRookSha}:installer/RookSetup.iss") -WorkingDirectory $canonicalRookRoot -OutputPath $reviewedInstallerPath
$stagedInstallerPath = Resolve-RequiredFile -Path (Join-Path $stagedRook 'installer\RookSetup.iss') -Label 'Staged installer source'
$reviewedInstallerIdentity = Get-FileIdentity -Path $reviewedInstallerPath
$stagedInstallerIdentity = Get-FileIdentity -Path $stagedInstallerPath
if ([long]$reviewedInstallerIdentity.size -ne [long]$stagedInstallerIdentity.size -or -not [string]::Equals([string]$reviewedInstallerIdentity.sha256,[string]$stagedInstallerIdentity.sha256,[StringComparison]::Ordinal)) {
    throw 'Staged installer source is not byte-identical to the reviewed Git blob'
}

$rookSourceInventory = New-InventoryProjection -Files @(Get-TreeInventory -Root $stagedRook -ExcludeGit)
$chirpSourceInventory = New-InventoryProjection -Files @(Get-TreeInventory -Root $stagedChirp -ExcludeGit)
$version = Get-VersionFromFile -Path (Join-Path $stagedRook 'mcp_server\pyproject.toml') -Pattern '(?m)^version\s*=\s*"([^"]+)"' -Label 'Python project'
$installerVersion = Get-VersionFromFile -Path $stagedInstallerPath -Pattern '(?m)^#define\s+MyAppVersion\s+"([^"]+)"' -Label 'installer'
$rookManagedVersion = Get-VersionFromFile -Path (Join-Path $stagedRook 'src\Rook\Rook.csproj') -Pattern '<Version>([^<]+)</Version>' -Label 'Rook managed project'
$rookBimVersion = Get-VersionFromFile -Path (Join-Path $stagedRook 'src\RookBim\RookBim.csproj') -Pattern '<Version>([^<]+)</Version>' -Label 'RookBim project'
foreach ($actualVersion in @($installerVersion,$rookManagedVersion,$rookBimVersion)) {
    if (-not [string]::Equals($version,$actualVersion,[StringComparison]::Ordinal)) { throw "Reviewed version disagreement: $version / $actualVersion" }
}

Assert-FileIdentityUnchanged -Expected $toolIdentities.PowerShellPath -Label 'PowerShellPath'
$stageRuntimeScript = Resolve-RequiredFile -Path (Join-Path $stagedRook 'scripts\python-runtime\stage-rook-python-runtime.ps1') -Label 'Python runtime staging script'
Invoke-ExactTool -Name 'stage-python-runtime' -FilePath $canonicalPowerShellPath -Arguments @('-NoProfile','-ExecutionPolicy','Bypass','-File',$stageRuntimeScript,'-RepoRoot',$stagedRook) -WorkingDirectory $stagedRook -Environment $null | Out-Null
Assert-StagedTrackedSourcesUnchanged -Label 'StagedRook' -Root $stagedRook -ExpectedSha $ExpectedRookSha
Assert-FileIdentityUnchanged -Expected $toolIdentities.PowerShellPath -Label 'PowerShellPath'
$buildWheelhouseScript = Resolve-RequiredFile -Path (Join-Path $stagedRook 'scripts\python-runtime\build-rook-python-wheelhouse.ps1') -Label 'Python wheelhouse build script'
Invoke-ExactTool -Name 'build-python-wheelhouse' -FilePath $canonicalPowerShellPath -Arguments @('-NoProfile','-ExecutionPolicy','Bypass','-File',$buildWheelhouseScript,'-Version',$version,'-RepoRoot',$stagedRook,'-ChirpRoot',$stagedChirp) -WorkingDirectory $stagedRook -Environment $null | Out-Null
Assert-StagedTrackedSourcesUnchanged -Label 'StagedRook' -Root $stagedRook -ExpectedSha $ExpectedRookSha
Assert-StagedTrackedSourcesUnchanged -Label 'StagedChirp' -Root $stagedChirp -ExpectedSha $ExpectedChirpSha
Assert-FileIdentityUnchanged -Expected $toolIdentities.PowerShellPath -Label 'PowerShellPath'
$validateWheelhouseScript = Resolve-RequiredFile -Path (Join-Path $stagedRook 'scripts\validate-python-wheelhouse.ps1') -Label 'Python wheelhouse validation script'
Invoke-ExactTool -Name 'validate-python-wheelhouse' -FilePath $canonicalPowerShellPath -Arguments @('-NoProfile','-ExecutionPolicy','Bypass','-File',$validateWheelhouseScript,'-Version',$version,'-RepoRoot',$stagedRook) -WorkingDirectory $stagedRook -Environment $null | Out-Null
$wheelhouseRoot = Resolve-RequiredDirectory -Path (Join-Path $stagedRook 'installer\runtime\python-wheelhouse') -Label 'Validated Python wheelhouse'
Assert-ContainmentWheelFixture -WheelhouseRoot $wheelhouseRoot -Version $version
$validatedWheelhouseProjection = New-InventoryProjection -Files @(Get-TreeInventory -Root $wheelhouseRoot)
Assert-StagedTrackedSourcesUnchanged -Label 'StagedRook' -Root $stagedRook -ExpectedSha $ExpectedRookSha
Assert-StagedTrackedSourcesUnchanged -Label 'StagedChirp' -Root $stagedChirp -ExpectedSha $ExpectedChirpSha

$ffmpegSourcePath = Resolve-RequiredFile -Path (Join-Path $stagedRook 'scripts\ffmpeg\rook-ffmpeg-source.json') -Label 'FFmpeg source identity'
$ffmpegSource = Get-Content -LiteralPath $ffmpegSourcePath -Raw | ConvertFrom-Json
$ffmpegVersion = [string]$ffmpegSource.version
if ([string]::IsNullOrWhiteSpace($ffmpegVersion)) { throw 'FFmpeg source identity has no version' }
Assert-FileIdentityUnchanged -Expected $toolIdentities.PowerShellPath -Label 'PowerShellPath'
Assert-FileIdentityUnchanged -Expected $toolIdentities.Msys2Bash -Label 'Msys2Bash'
$buildFfmpegScript = Resolve-RequiredFile -Path (Join-Path $stagedRook 'scripts\ffmpeg\build-rook-ffmpeg.ps1') -Label 'FFmpeg build script'
Invoke-ExactTool -Name 'build-ffmpeg' -FilePath $canonicalPowerShellPath -Arguments @('-NoProfile','-ExecutionPolicy','Bypass','-File',$buildFfmpegScript,'-RepoRoot',$stagedRook,'-Msys2Bash',$canonicalMsys2Bash,'-InstallPayload') -WorkingDirectory $stagedRook -Environment $null | Out-Null
Assert-StagedTrackedSourcesUnchanged -Label 'StagedRook' -Root $stagedRook -ExpectedSha $ExpectedRookSha -AllowedChangedPaths $RookTrackedBuildOutputPaths
$trackedFfmpegOutputProjection = Get-SelectedFileProjection -Root $stagedRook -RelativePaths $RookTrackedBuildOutputPaths -MissingLabel 'Tracked FFmpeg build output'
$ffmpegManifestPath = Join-Path $stagedRook "artifacts\ffmpeg\ffmpeg-$ffmpegVersion-rook-minimal\rook-ffmpeg-source-bundle-manifest.json"
$ffmpegManifestPath = Resolve-RequiredFile -Path $ffmpegManifestPath -Label 'Generated FFmpeg source-bundle manifest'
$ffmpegManifestIdentity = Get-FileIdentity -Path $ffmpegManifestPath
Assert-FileIdentityUnchanged -Expected $toolIdentities.PowerShellPath -Label 'PowerShellPath'
$validateFfmpegScript = Resolve-RequiredFile -Path (Join-Path $stagedRook 'scripts\validate-ffmpeg-bundle.ps1') -Label 'FFmpeg validation script'
Invoke-ExactTool -Name 'validate-ffmpeg' -FilePath $canonicalPowerShellPath -Arguments @('-NoProfile','-ExecutionPolicy','Bypass','-File',$validateFfmpegScript,'-RepoRoot',$stagedRook,'-SourceBundleManifestPath',$ffmpegManifestPath) -WorkingDirectory $stagedRook -Environment $null | Out-Null
Assert-FileIdentityUnchanged -Expected $ffmpegManifestIdentity -Label 'Validated FFmpeg manifest'
Assert-StagedTrackedSourcesUnchanged -Label 'StagedRook' -Root $stagedRook -ExpectedSha $ExpectedRookSha -AllowedChangedPaths $RookTrackedBuildOutputPaths
$currentTrackedFfmpegOutputProjection = Get-SelectedFileProjection -Root $stagedRook -RelativePaths $RookTrackedBuildOutputPaths -MissingLabel 'Tracked FFmpeg build output'
Assert-ProjectionUnchanged -Expected $trackedFfmpegOutputProjection -Current $currentTrackedFfmpegOutputProjection -Label 'Tracked FFmpeg build output'

$privateNative = New-PrivateNativeEnvironment -ArtifactRoot $canonicalArtifact -CanonicalCmd $script:CanonicalCmdPath
$privateEnvironment = $privateNative.environment
foreach ($name in $NativeEnvironmentScrubNames) {
    if ($privateEnvironment.ContainsKey($name)) { throw "Private pre-vcvars environment retained scrubbed name $name" }
}
$vsRoot = Get-NativeVsRoot -VcvarsPath $canonicalVcvarsallPath
$nativeProbeRoot = Join-Path $canonicalArtifact 'native-environment'
New-Item -ItemType Directory -Path $nativeProbeRoot | Out-Null
$preEnvironmentPath = Join-Path $nativeProbeRoot 'pre-vcvars.env'
$postEnvironmentPath = Join-Path $nativeProbeRoot 'post-vcvars.env'
$probeBatchPath = Join-Path $nativeProbeRoot 'probe-vcvars.cmd'
$probeBatch = @(
    '@echo off',
    'set "PROMPT="',
    ('set > ' + (ConvertTo-CmdQuotedArgument -Value $preEnvironmentPath)),
    ('call ' + (ConvertTo-CmdQuotedArgument -Value $canonicalVcvarsallPath) + ' x64 -vcvars_ver=' + $NativeVcvarsSelector),
    'if errorlevel 1 exit /b %errorlevel%',
    ('set > ' + (ConvertTo-CmdQuotedArgument -Value $postEnvironmentPath)),
    'exit /b 0'
) -join "`r`n"
Write-Utf8NoBom -Path $probeBatchPath -Text ($probeBatch + "`r`n")
Assert-FileIdentityUnchanged -Expected $toolIdentities.CmdPath -Label 'CmdPath'
Assert-FileIdentityUnchanged -Expected $toolIdentities.VcvarsallPath -Label 'VcvarsallPath'
Invoke-External -Name 'native-environment' -FilePath $script:CanonicalCmdPath -Arguments @('/d','/c',$probeBatchPath) -WorkingDirectory $stagedRook -Environment $privateEnvironment -TimeoutMilliseconds 120000 | Out-Null
$capturedPreEnvironment = Read-EnvironmentFile -Path $preEnvironmentPath
Assert-EnvironmentKeySet -Environment $capturedPreEnvironment -ExpectedNames $NativeEnvironmentAllowlist -Label 'Captured pre-vcvars environment'
foreach ($entry in $privateEnvironment.GetEnumerator()) {
    if (-not [string]::Equals($capturedPreEnvironment[$entry.Key],$entry.Value,[StringComparison]::Ordinal)) { throw "Captured pre-vcvars value mismatch for $($entry.Key)" }
}
$capturedPostEnvironment = Read-EnvironmentFile -Path $postEnvironmentPath
$capturedNativeProjection = Assert-CapturedNativeEnvironment -Captured $capturedPostEnvironment -VsRoot $vsRoot -SystemRoot $privateNative.system_root -ProgramFilesRoot $privateNative.program_files -ProgramFilesX86Root $privateNative.program_files_x86 -HostileValues $hostileValues
Assert-StagedTrackedSourcesUnchanged -Label 'StagedRook' -Root $stagedRook -ExpectedSha $ExpectedRookSha -AllowedChangedPaths $RookTrackedBuildOutputPaths
$currentTrackedFfmpegOutputProjection = Get-SelectedFileProjection -Root $stagedRook -RelativePaths $RookTrackedBuildOutputPaths -MissingLabel 'Tracked FFmpeg build output'
Assert-ProjectionUnchanged -Expected $trackedFfmpegOutputProjection -Current $currentTrackedFfmpegOutputProjection -Label 'Tracked FFmpeg build output'
$capturedVcToolsRoot = Get-CanonicalExistingPathSegment -Path $capturedPostEnvironment['VCToolsInstallDir'] -Label 'VCToolsInstallDir'
$nativeCompilerPath = Resolve-RequiredFile -Path (Join-Path $capturedVcToolsRoot 'bin\Hostx64\x64\cl.exe') -Label 'Selected native compiler'
$nativeLinkerPath = Resolve-RequiredFile -Path (Join-Path $capturedVcToolsRoot 'bin\Hostx64\x64\link.exe') -Label 'Selected native linker'
$nativeCompilerIdentity = Get-FileIdentity -Path $nativeCompilerPath
$nativeLinkerIdentity = Get-FileIdentity -Path $nativeLinkerPath

$currentOcctBuildProjection = Get-SelectedFileProjection -Root $canonicalOcctRoot -RelativePaths $occtBuildRelativePaths -MissingLabel 'OCCT import input'
$currentOcctRuntimeProjection = Get-SelectedFileProjection -Root $canonicalOcctRuntimeRoot -RelativePaths $installerOcctDlls -MissingLabel 'OCCT runtime DLL'
Assert-ProjectionUnchanged -Expected $initialOcctBuildProjection -Current $currentOcctBuildProjection -Label 'OCCT input'
Assert-ProjectionUnchanged -Expected $initialOcctRuntimeProjection -Current $currentOcctRuntimeProjection -Label 'OCCT runtime input'
Assert-RhinoSdkAuthorityUnchanged -ExpectedInstallPath $rhinoSdkInstallPath -ExpectedPropertySheetIdentity $rhinoSdkPropertySheetIdentity
Assert-FileIdentityUnchanged -Expected $toolIdentities.VcvarsallPath -Label 'VcvarsallPath'
Assert-FileIdentityUnchanged -Expected $toolIdentities.MsbuildPath -Label 'MsbuildPath'
Assert-FileIdentityUnchanged -Expected $nativeCompilerIdentity -Label 'Selected native compiler'
Assert-FileIdentityUnchanged -Expected $nativeLinkerIdentity -Label 'Selected native linker'

$stagedNativeProject = Resolve-RequiredFile -Path (Join-Path $stagedRook 'src\RookNative\RookNative.vcxproj') -Label 'Staged native project'
$msbuildArguments = @(
    $stagedNativeProject,'/t:Build','/p:Configuration=Release','/p:Platform=x64',
    "/p:VCToolsVersion=$NativeToolsetVersion","/p:OcctRoot=$canonicalOcctRoot"
) + $MsbuildImportDisableArguments
Invoke-ExactTool -Name 'native-build' -FilePath $canonicalMsbuildPath -Arguments $msbuildArguments -WorkingDirectory $stagedRook -Environment $capturedPostEnvironment | Out-Null
Resolve-RequiredFile -Path (Join-Path $stagedRook 'src\RookNative\bin\Release\x64\RookNative.rhp') -Label 'Built native Rook plug-in' | Out-Null
Assert-FileIdentityUnchanged -Expected $nativeCompilerIdentity -Label 'Selected native compiler'
Assert-FileIdentityUnchanged -Expected $nativeLinkerIdentity -Label 'Selected native linker'
Assert-StagedTrackedSourcesUnchanged -Label 'StagedRook' -Root $stagedRook -ExpectedSha $ExpectedRookSha -AllowedChangedPaths $RookTrackedBuildOutputPaths
$currentTrackedFfmpegOutputProjection = Get-SelectedFileProjection -Root $stagedRook -RelativePaths $RookTrackedBuildOutputPaths -MissingLabel 'Tracked FFmpeg build output'
Assert-ProjectionUnchanged -Expected $trackedFfmpegOutputProjection -Current $currentTrackedFfmpegOutputProjection -Label 'Tracked FFmpeg build output'

Assert-FileIdentityUnchanged -Expected $toolIdentities.DotnetPath -Label 'DotnetPath'
$dotnetVersionResult = Invoke-ExactTool -Name 'dotnet-version' -FilePath $canonicalDotnetPath -Arguments @('--version') -WorkingDirectory $stagedRook -Environment $null -TimeoutMilliseconds 120000
$dotnetVersion = ([string]$dotnetVersionResult.stdout).Trim()
if ([string]::IsNullOrWhiteSpace($dotnetVersion)) { throw 'DotnetPath --version returned an empty version' }
Assert-StagedTrackedSourcesUnchanged -Label 'StagedRook' -Root $stagedRook -ExpectedSha $ExpectedRookSha -AllowedChangedPaths $RookTrackedBuildOutputPaths
$currentTrackedFfmpegOutputProjection = Get-SelectedFileProjection -Root $stagedRook -RelativePaths $RookTrackedBuildOutputPaths -MissingLabel 'Tracked FFmpeg build output'
Assert-ProjectionUnchanged -Expected $trackedFfmpegOutputProjection -Current $currentTrackedFfmpegOutputProjection -Label 'Tracked FFmpeg build output'
$rookProject = Resolve-RequiredFile -Path (Join-Path $stagedRook 'src\Rook\Rook.csproj') -Label 'Staged Rook managed project'
$rookBimProject = Resolve-RequiredFile -Path (Join-Path $stagedRook 'src\RookBim\RookBim.csproj') -Label 'Staged RookBim project'
$currentRhinoManagedProjection = Get-SelectedFileProjection -Root $canonicalRhinoSystemDir -RelativePaths $RhinoManagedReferenceFiles -MissingLabel 'Rhino managed reference'
Assert-ProjectionUnchanged -Expected $rhinoManagedProjection -Current $currentRhinoManagedProjection -Label 'Rhino managed reference'
Assert-Condition -Condition (-not (Test-Path -LiteralPath $inertRhinoPluginDir)) -Message "inert RhinoPluginDir was created before Rook managed build: $inertRhinoPluginDir"
Assert-FileIdentityUnchanged -Expected $toolIdentities.DotnetPath -Label 'DotnetPath'
$rookManagedArguments = @('build',$rookProject,'-c','Release',"-p:RhinoPluginDir=$inertRhinoPluginDir","-p:RhinoSystemDir=$canonicalRhinoSystemDir")
Invoke-ExactTool -Name 'build-rook-managed' -FilePath $canonicalDotnetPath -Arguments $rookManagedArguments -WorkingDirectory $stagedRook -Environment $null | Out-Null
Assert-StagedTrackedSourcesUnchanged -Label 'StagedRook' -Root $stagedRook -ExpectedSha $ExpectedRookSha -AllowedChangedPaths $RookTrackedBuildOutputPaths
$currentTrackedFfmpegOutputProjection = Get-SelectedFileProjection -Root $stagedRook -RelativePaths $RookTrackedBuildOutputPaths -MissingLabel 'Tracked FFmpeg build output'
Assert-ProjectionUnchanged -Expected $trackedFfmpegOutputProjection -Current $currentTrackedFfmpegOutputProjection -Label 'Tracked FFmpeg build output'
$currentRhinoManagedProjection = Get-SelectedFileProjection -Root $canonicalRhinoSystemDir -RelativePaths $RhinoManagedReferenceFiles -MissingLabel 'Rhino managed reference'
Assert-ProjectionUnchanged -Expected $rhinoManagedProjection -Current $currentRhinoManagedProjection -Label 'Rhino managed reference'
Assert-Condition -Condition (-not (Test-Path -LiteralPath $inertRhinoPluginDir)) -Message "inert RhinoPluginDir was created by Rook managed build: $inertRhinoPluginDir"
Assert-FileIdentityUnchanged -Expected $toolIdentities.DotnetPath -Label 'DotnetPath'
$currentRevitProjection = Get-SelectedFileProjection -Root $canonicalRevitInstallDir -RelativePaths $RevitReferenceFiles -MissingLabel 'Revit reference'
Assert-ProjectionUnchanged -Expected $revitProjection -Current $currentRevitProjection -Label 'Revit reference'
$rookBimArguments = @('build',$rookBimProject,'-c','Release',"-p:RhinoPluginDir=$inertRhinoPluginDir","-p:RhinoSystemDir=$canonicalRhinoSystemDir","-p:RevitInstallDir=$canonicalRevitInstallDir")
Invoke-ExactTool -Name 'build-rookbim-managed' -FilePath $canonicalDotnetPath -Arguments $rookBimArguments -WorkingDirectory $stagedRook -Environment $null | Out-Null
Assert-StagedTrackedSourcesUnchanged -Label 'StagedRook' -Root $stagedRook -ExpectedSha $ExpectedRookSha -AllowedChangedPaths $RookTrackedBuildOutputPaths
$currentTrackedFfmpegOutputProjection = Get-SelectedFileProjection -Root $stagedRook -RelativePaths $RookTrackedBuildOutputPaths -MissingLabel 'Tracked FFmpeg build output'
Assert-ProjectionUnchanged -Expected $trackedFfmpegOutputProjection -Current $currentTrackedFfmpegOutputProjection -Label 'Tracked FFmpeg build output'
$currentRhinoManagedProjection = Get-SelectedFileProjection -Root $canonicalRhinoSystemDir -RelativePaths $RhinoManagedReferenceFiles -MissingLabel 'Rhino managed reference'
$currentRevitProjection = Get-SelectedFileProjection -Root $canonicalRevitInstallDir -RelativePaths $RevitReferenceFiles -MissingLabel 'Revit reference'
Assert-ProjectionUnchanged -Expected $rhinoManagedProjection -Current $currentRhinoManagedProjection -Label 'Rhino managed reference'
Assert-ProjectionUnchanged -Expected $revitProjection -Current $currentRevitProjection -Label 'Revit reference'
Assert-Condition -Condition (-not (Test-Path -LiteralPath $inertRhinoPluginDir)) -Message "inert RhinoPluginDir was created by RookBim managed build: $inertRhinoPluginDir"

Assert-FileIdentityUnchanged -Expected $toolIdentities.IsccPath -Label 'IsccPath'
$currentWheelhouseProjection = New-InventoryProjection -Files @(Get-TreeInventory -Root $wheelhouseRoot)
Assert-ProjectionUnchanged -Expected $validatedWheelhouseProjection -Current $currentWheelhouseProjection -Label 'Validated Python wheelhouse'
Assert-FileIdentityUnchanged -Expected $ffmpegManifestIdentity -Label 'Validated FFmpeg manifest'
$currentVcRedistProjection = Get-SelectedFileProjection -Root $canonicalVcRedistRoot -RelativePaths $VcRedistFiles -MissingLabel 'VC redistributable input'
$currentOcctRuntimeProjection = Get-SelectedFileProjection -Root $canonicalOcctRuntimeRoot -RelativePaths $installerOcctDlls -MissingLabel 'OCCT runtime DLL'
Assert-ProjectionUnchanged -Expected $vcRedistProjection -Current $currentVcRedistProjection -Label 'VC redistributable input'
Assert-ProjectionUnchanged -Expected $initialOcctRuntimeProjection -Current $currentOcctRuntimeProjection -Label 'OCCT runtime input'
$isccArguments = @(
    "/DMyAppVersion=$version",
    "/DVcRedistRoot=$canonicalVcRedistRoot",
    "/DOcctRuntimeRoot=$canonicalOcctRuntimeRoot",
    $stagedInstallerPath
)
Invoke-ExactTool -Name 'build-installer' -FilePath $canonicalIsccPath -Arguments $isccArguments -WorkingDirectory (Split-Path -Parent $stagedInstallerPath) -Environment $null | Out-Null
$currentWheelhouseProjection = New-InventoryProjection -Files @(Get-TreeInventory -Root $wheelhouseRoot)
Assert-ProjectionUnchanged -Expected $validatedWheelhouseProjection -Current $currentWheelhouseProjection -Label 'Validated Python wheelhouse'
Assert-FileIdentityUnchanged -Expected $ffmpegManifestIdentity -Label 'Validated FFmpeg manifest'
Assert-StagedTrackedSourcesUnchanged -Label 'StagedRook' -Root $stagedRook -ExpectedSha $ExpectedRookSha -AllowedChangedPaths $RookTrackedBuildOutputPaths
$currentTrackedFfmpegOutputProjection = Get-SelectedFileProjection -Root $stagedRook -RelativePaths $RookTrackedBuildOutputPaths -MissingLabel 'Tracked FFmpeg build output'
Assert-ProjectionUnchanged -Expected $trackedFfmpegOutputProjection -Current $currentTrackedFfmpegOutputProjection -Label 'Tracked FFmpeg build output'
$currentVcRedistProjection = Get-SelectedFileProjection -Root $canonicalVcRedistRoot -RelativePaths $VcRedistFiles -MissingLabel 'VC redistributable input'
$currentOcctRuntimeProjection = Get-SelectedFileProjection -Root $canonicalOcctRuntimeRoot -RelativePaths $installerOcctDlls -MissingLabel 'OCCT runtime DLL'
Assert-ProjectionUnchanged -Expected $vcRedistProjection -Current $currentVcRedistProjection -Label 'VC redistributable input'
Assert-ProjectionUnchanged -Expected $initialOcctRuntimeProjection -Current $currentOcctRuntimeProjection -Label 'OCCT runtime input'
$builtInstallerPath = Resolve-RequiredFile -Path (Join-Path $stagedRook "installer\output\Rook-Setup-$version.exe") -Label 'Built containment installer'

$privatePythonPath = Resolve-RequiredFile -Path (Join-Path $stagedRook 'installer\runtime\python\cpython-3.11.9\python.exe') -Label 'Staged private Python executable'
$privatePythonVersionResult = Invoke-ExactTool -Name 'private-python-version' -FilePath $privatePythonPath -Arguments @('--version') -WorkingDirectory (Split-Path -Parent $privatePythonPath) -Environment $null -TimeoutMilliseconds 120000
$privatePythonVersionText = (([string]$privatePythonVersionResult.stdout + "`n" + [string]$privatePythonVersionResult.stderr).Trim())
$privatePythonVersionMatch = [regex]::Match($privatePythonVersionText,'(?m)^Python\s+([0-9]+\.[0-9]+\.[0-9]+)\s*$')
if (-not $privatePythonVersionMatch.Success) { throw "Private Python version probe was malformed: $privatePythonVersionText" }
$privatePythonVersion = $privatePythonVersionMatch.Groups[1].Value
if (-not [string]::Equals($privatePythonVersion,$RequiredPrivatePythonVersion,[StringComparison]::Ordinal)) { throw "Private Python version mismatch: expected $RequiredPrivatePythonVersion, got $privatePythonVersion" }
$pthFiles = @(Get-OrdinalSortedStrings -Values @(Get-ChildItem -LiteralPath (Split-Path -Parent $privatePythonPath) -Recurse -File -Filter '*._pth' | ForEach-Object { Get-RelativePathText -Root (Split-Path -Parent $privatePythonPath) -Path $_.FullName }))
if ($pthFiles.Count -ne 0) { throw "Full private Python runtime must not contain *._pth files: $($pthFiles -join ', ')" }

$stagedInstallerAfterBuild = Get-FileIdentity -Path $stagedInstallerPath
if ([long]$stagedInstallerAfterBuild.size -ne [long]$reviewedInstallerIdentity.size -or -not [string]::Equals([string]$stagedInstallerAfterBuild.sha256,[string]$reviewedInstallerIdentity.sha256,[StringComparison]::Ordinal)) {
    throw 'Tracked staged installer changed during candidate construction'
}
$livePluginAfter = Get-LivePluginProjection -Path $livePluginPath
if (-not [string]::Equals([string]$livePluginBefore.sha256,[string]$livePluginAfter.sha256,[StringComparison]::Ordinal)) {
    throw 'live RookNative plug-in projection changed during candidate construction'
}
Assert-Condition -Condition (-not (Test-Path -LiteralPath $inertRhinoPluginDir)) -Message "inert RhinoPluginDir was created during candidate construction: $inertRhinoPluginDir"

Assert-OriginalSourceState -Label 'Rook' -Expected $rookInitialState
Assert-OriginalSourceState -Label 'Chirp' -Expected $chirpInitialState
Assert-StagedTrackedSourcesUnchanged -Label 'StagedRook' -Root $stagedRook -ExpectedSha $ExpectedRookSha -AllowedChangedPaths $RookTrackedBuildOutputPaths
Assert-StagedTrackedSourcesUnchanged -Label 'StagedChirp' -Root $stagedChirp -ExpectedSha $ExpectedChirpSha
$finalTrackedFfmpegOutputProjection = Get-SelectedFileProjection -Root $stagedRook -RelativePaths $RookTrackedBuildOutputPaths -MissingLabel 'Tracked FFmpeg build output'
Assert-ProjectionUnchanged -Expected $trackedFfmpegOutputProjection -Current $finalTrackedFfmpegOutputProjection -Label 'Tracked FFmpeg build output'
$finalWheelhouseProjection = New-InventoryProjection -Files @(Get-TreeInventory -Root $wheelhouseRoot)
Assert-ProjectionUnchanged -Expected $validatedWheelhouseProjection -Current $finalWheelhouseProjection -Label 'Validated Python wheelhouse'
Assert-FileIdentityUnchanged -Expected $ffmpegManifestIdentity -Label 'Validated FFmpeg manifest'
foreach ($entry in $toolIdentities.GetEnumerator()) { Assert-FileIdentityUnchanged -Expected $entry.Value -Label $entry.Key }
Assert-RhinoSdkAuthorityUnchanged -ExpectedInstallPath $rhinoSdkInstallPath -ExpectedPropertySheetIdentity $rhinoSdkPropertySheetIdentity
Assert-FileIdentityUnchanged -Expected $nativeCompilerIdentity -Label 'Selected native compiler'
Assert-FileIdentityUnchanged -Expected $nativeLinkerIdentity -Label 'Selected native linker'
$finalOcctBuildProjection = Get-SelectedFileProjection -Root $canonicalOcctRoot -RelativePaths $occtBuildRelativePaths -MissingLabel 'OCCT import input'
$finalOcctRuntimeProjection = Get-SelectedFileProjection -Root $canonicalOcctRuntimeRoot -RelativePaths $installerOcctDlls -MissingLabel 'OCCT runtime DLL'
$finalRhinoManagedProjection = Get-SelectedFileProjection -Root $canonicalRhinoSystemDir -RelativePaths $RhinoManagedReferenceFiles -MissingLabel 'Rhino managed reference'
$finalRevitProjection = Get-SelectedFileProjection -Root $canonicalRevitInstallDir -RelativePaths $RevitReferenceFiles -MissingLabel 'Revit reference'
$finalVcRedistProjection = Get-SelectedFileProjection -Root $canonicalVcRedistRoot -RelativePaths $VcRedistFiles -MissingLabel 'VC redistributable input'
Assert-ProjectionUnchanged -Expected $initialOcctBuildProjection -Current $finalOcctBuildProjection -Label 'OCCT input'
Assert-ProjectionUnchanged -Expected $initialOcctRuntimeProjection -Current $finalOcctRuntimeProjection -Label 'OCCT runtime input'
Assert-ProjectionUnchanged -Expected $rhinoManagedProjection -Current $finalRhinoManagedProjection -Label 'Rhino managed reference'
Assert-ProjectionUnchanged -Expected $revitProjection -Current $finalRevitProjection -Label 'Revit reference'
Assert-ProjectionUnchanged -Expected $vcRedistProjection -Current $finalVcRedistProjection -Label 'VC redistributable input'

$ffmpegPayloadProjection = New-InventoryProjection -Files @(Get-TreeInventory -Root (Join-Path $stagedRook 'third_party\ffmpeg'))
$buildInventory = New-InventoryProjection -Files @(Get-TreeInventory -Root $stageRoot -ExcludeGit)
$outputInventory = New-InventoryProjection -Files @(Get-TreeInventory -Root $canonicalArtifact -ExcludeGit)
$buildCompletedUtc = [DateTime]::UtcNow.ToString('o')
$commands = @($script:CommandRecords.ToArray())
$privatePythonIdentity = Get-FileIdentity -Path $privatePythonPath
$builtInstallerIdentity = Get-FileIdentity -Path $builtInstallerPath
$ffmpegSourceIdentity = Get-FileIdentity -Path $ffmpegSourcePath
$nativeEnvironmentProjection = Get-EnvironmentProjection -Environment $privateEnvironment

$candidateIdentity = [ordered]@{
    schema_version = 1
    non_publishable = $true
    product_version = $version
    build = [ordered]@{
        started_utc = $buildStartedUtc
        completed_utc = $buildCompletedUtc
    }
    sources = [ordered]@{
        rook = [ordered]@{
            root = $canonicalRookRoot
            branch = $ExpectedBranch
            sha = $ExpectedRookSha
            clean = $true
            local_source_clone_path = $stagedRook
            stage_path = $stagedRook
            tracked_build_output_paths = @($RookTrackedBuildOutputPaths)
            source_archive_sha256 = Get-LowerSha256 -Path $rookArchivePath
            source_tree_digest = $rookSourceInventory.digest
        }
        chirp = [ordered]@{
            root = $canonicalChirpRoot
            branch = [string]$chirpInitialState.branch
            sha = $ExpectedChirpSha
            clean = $true
            local_source_clone_path = $stagedChirp
            stage_path = $stagedChirp
            source_archive_sha256 = Get-LowerSha256 -Path $chirpArchivePath
            source_tree_digest = $chirpSourceInventory.digest
        }
    }
    tools = $toolIdentities
    inputs = [ordered]@{
        python_wheelhouse = [ordered]@{
            relative_path = Get-RelativePathText -Root $canonicalArtifact -Path $wheelhouseRoot
            validated_payload = $validatedWheelhouseProjection
        }
        native_msvc = [ordered]@{
            vcvars_selector = $NativeVcvarsSelector
            vc_tools_version = $NativeToolsetVersion
            visual_studio_root = $vsRoot
            compiler = $nativeCompilerIdentity
            linker = $nativeLinkerIdentity
        }
        native_rhino_sdk = [ordered]@{
            registry_key = $RhinoSdkRegistryKey
            install_path = $rhinoSdkInstallPath
            property_sheet = $rhinoSdkPropertySheetIdentity
        }
        dotnet = [ordered]@{
            version = $dotnetVersion
            executable = $toolIdentities.DotnetPath
        }
        rhino_managed_references = [ordered]@{
            root = $canonicalRhinoSystemDir
            projection = $rhinoManagedProjection
        }
        revit_references = [ordered]@{
            root = $canonicalRevitInstallDir
            projection = $revitProjection
        }
        vc_redist = [ordered]@{
            root = $canonicalVcRedistRoot
            projection = $vcRedistProjection
        }
        occt = [ordered]@{
            build_root = $canonicalOcctRoot
            runtime_root = $canonicalOcctRuntimeRoot
            msbuild_property = "/p:OcctRoot=$canonicalOcctRoot"
            consumed_header_and_import_libraries = $initialOcctBuildProjection
            consumed_runtime_dlls = $initialOcctRuntimeProjection
        }
        ffmpeg = [ordered]@{
            version = $ffmpegVersion
            source_identity = $ffmpegSourceIdentity
            source_bundle_manifest = $ffmpegManifestIdentity
            installed_payload = $ffmpegPayloadProjection
            tracked_build_outputs = $trackedFfmpegOutputProjection
        }
    }
    native_environment = [ordered]@{
        contract_version = 1
        input_allowlist = @(Get-OrdinalSortedStrings -Values $NativeEnvironmentAllowlist)
        scrub_names = @(Get-OrdinalSortedStrings -Values $NativeEnvironmentScrubNames)
        pre_vcvars = $nativeEnvironmentProjection
        captured = $capturedNativeProjection
        import_disable_arguments = @($MsbuildImportDisableArguments)
        msbuild_executable = $canonicalMsbuildPath
        msbuild_arguments = @($msbuildArguments)
        msbuild_occt_root = $canonicalOcctRoot
    }
    private_python = [ordered]@{
        relative_path = Get-RelativePathText -Root $canonicalArtifact -Path $privatePythonPath
        version = $privatePythonVersion
        sha256 = $privatePythonIdentity.sha256
        pth_files = @($pthFiles)
    }
    managed = [ordered]@{
        inert_rhino_plugin_dir = $inertRhinoPluginDir
        rook_arguments = @($rookManagedArguments)
        rookbim_arguments = @($rookBimArguments)
        live_plugin = [ordered]@{
            path = $livePluginPath
            before_sha256 = $livePluginBefore.sha256
            after_sha256 = $livePluginAfter.sha256
            projection = $livePluginBefore.projection
        }
    }
    installer = [ordered]@{
        relative_path = Get-RelativePathText -Root $canonicalArtifact -Path $builtInstallerPath
        sha256 = $builtInstallerIdentity.sha256
        source_sha256 = $reviewedInstallerIdentity.sha256
        staged_sha256 = $stagedInstallerAfterBuild.sha256
        source_size = $reviewedInstallerIdentity.size
        staged_size = $stagedInstallerAfterBuild.size
    }
    commands = $commands
    inventories = [ordered]@{
        source_inventory = [ordered]@{
            rook = $rookSourceInventory
            chirp = $chirpSourceInventory
        }
        build_inventory = $buildInventory
        output_inventory = $outputInventory
    }
}

$candidateIdentityPath = Join-Path $canonicalArtifact 'containment-candidate.json'
$candidateSidecarPath = Join-Path $canonicalArtifact 'containment-candidate.sha256'
Assert-Condition -Condition (-not (Test-Path -LiteralPath $candidateIdentityPath)) -Message "Candidate identity already exists: $candidateIdentityPath"
Assert-Condition -Condition (-not (Test-Path -LiteralPath $candidateSidecarPath)) -Message "Candidate sidecar already exists: $candidateSidecarPath"
$canonicalIdentityJson = ConvertTo-CanonicalJson -Value $candidateIdentity
Write-Utf8NoBom -Path $candidateIdentityPath -Text $canonicalIdentityJson
$identitySha256 = Get-LowerSha256 -Path $candidateIdentityPath
[System.IO.File]::WriteAllText($candidateSidecarPath, "$identitySha256  containment-candidate.json`n", [System.Text.Encoding]::ASCII)
Write-Host "Non-publishable containment candidate written to $canonicalArtifact"
Write-Host "Candidate identity SHA-256: $identitySha256"
