$ErrorActionPreference = 'Stop'

$TestRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $TestRoot)
$ProfileScript = Join-Path $RepoRoot 'scripts\register-managed-runtime-profile.ps1'

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Assert-Contains {
    param([string]$Text, [string]$Expected, [string]$Message)
    Assert-True -Condition $Text.Contains($Expected) -Message $Message
}

function Get-PowerShellExecutable {
    $pwsh = Get-Command pwsh -ErrorAction SilentlyContinue
    if ($pwsh) {
        return $pwsh.Source
    }

    return (Get-Command powershell -ErrorAction Stop).Source
}

function ConvertTo-ProcessArgument {
    param([string]$Value)

    if ($null -eq $Value) {
        return '""'
    }

    if ($Value -notmatch '[\s"]') {
        return $Value
    }

    $escaped = $Value -replace '(\\*)"', '$1$1\"'
    $escaped = $escaped -replace '(\\+)$', '$1$1'
    return '"' + $escaped + '"'
}

function Invoke-ScriptProcess {
    param([string[]]$Arguments)

    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = Get-PowerShellExecutable
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false

    $allArguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass') + $Arguments
    $psi.Arguments = ($allArguments | ForEach-Object { ConvertTo-ProcessArgument $_ }) -join ' '

    $process = [System.Diagnostics.Process]::Start($psi)
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()

    return [pscustomobject]@{
        ExitCode = $process.ExitCode
        Output = ($stdout + "`n" + $stderr)
    }
}

function Test-ProfileScriptPinsKnownManagedPlugins {
    Assert-True -Condition (Test-Path $ProfileScript) -Message 'Missing managed runtime profile switcher script.'
    $content = Get-Content -LiteralPath $ProfileScript -Raw

    Assert-Contains -Text $content -Expected "ValidateSet('NetCore', 'NetFramework')" -Message 'Runtime profile selection must be explicit.'
    Assert-Contains -Text $content -Expected 'Rhino.Inside uses the host application' -Message 'Script must document the Rhino.Inside runtime constraint.'
    Assert-Contains -Text $content -Expected 'b7e4a8c9-1f62-4c7e-9a2b-5d4e8f1c3a7b' -Message 'Rook companion GUID must be pinned.'
    Assert-Contains -Text $content -Expected 'a9b8c7d6-e5f4-3a2b-1c0d-9e8f7a6b5c4d' -Message 'RookRoads GUID must be pinned.'
    Assert-Contains -Text $content -Expected '4c23ee05-6ff3-47f6-acb4-475968e37cde' -Message 'SA_Banana GUID must be pinned.'
    Assert-Contains -Text $content -Expected 'Split-Path -Leaf $Profile.NetFrameworkSourceDir' -Message 'NetFramework profile must register the runtime payload directory.'
    Assert-Contains -Text $content -Expected 'Split-Path -Leaf $Profile.NetCoreSourceDir' -Message 'NetCore profile must register the runtime payload directory.'
    Assert-Contains -Text $content -Expected 'Set-ItemProperty -Path $plugInKey -Name ''FileName''' -Message 'Script must update the Rhino PlugIn FileName registry value.'
    Assert-Contains -Text $content -Expected '[switch]$DryRun' -Message 'Script must support dry-run verification without registry writes.'
}

function Test-DryRunNetFrameworkProfile {
    $result = Invoke-ScriptProcess -Arguments @(
        '-File', $ProfileScript,
        '-Runtime', 'NetFramework',
        '-DryRun'
    )

    Assert-True -Condition ($result.ExitCode -eq 0) -Message "NetFramework dry-run failed. Output: $($result.Output)"
    Assert-Contains -Text $result.Output -Expected 'Switching managed Rhino plug-ins to NetFramework profile' -Message 'Dry-run must report NetFramework profile.'
    Assert-Contains -Text $result.Output -Expected 'RookNative\net48\Rook.rhp' -Message 'Rook dry-run must target net48 Rook companion.'
    Assert-Contains -Text $result.Output -Expected 'RookRC\net48\RookRC.rhp' -Message 'RookRoads dry-run must target net48 RookRC.'
    Assert-Contains -Text $result.Output -Expected 'SA_Banana\net48\SA_Banana.rhp' -Message 'SA_Banana dry-run must target net48 SA_Banana.'
}

function Test-DryRunNetCoreProfile {
    $result = Invoke-ScriptProcess -Arguments @(
        '-File', $ProfileScript,
        '-Runtime', 'NetCore',
        '-DryRun',
        '-Plugin', 'Rook'
    )

    Assert-True -Condition ($result.ExitCode -eq 0) -Message "NetCore dry-run failed. Output: $($result.Output)"
    Assert-Contains -Text $result.Output -Expected 'Switching managed Rhino plug-ins to NetCore profile' -Message 'Dry-run must report NetCore profile.'
    Assert-Contains -Text $result.Output -Expected 'RookNative\net7.0\Rook.rhp' -Message 'NetCore dry-run must target net7.0 Rook companion.'
}

Test-ProfileScriptPinsKnownManagedPlugins
Test-DryRunNetFrameworkProfile
Test-DryRunNetCoreProfile

Write-Host 'Managed runtime profile guard tests passed.'
