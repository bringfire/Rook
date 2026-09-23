param(
    [ValidateSet('All', 'Metadata', 'Guidance', 'Workflow')]
    [string]$Area = 'All'
)

$ErrorActionPreference = 'Stop'

$TestRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $TestRoot)
$PublicRepository = 'https://github.com/bringfire/rook-release'
$PublicReleases = "$PublicRepository/releases"

function Get-RepoPath {
    param([string]$RelativePath)
    return Join-Path $RepoRoot ($RelativePath -replace '/', '\')
}

function Get-Text {
    param([string]$RelativePath)
    return (Get-Content -LiteralPath (Get-RepoPath $RelativePath) -Raw) -replace "`r`n", "`n"
}

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Assert-Contains {
    param([string]$Text, [string]$Expected, [string]$Message)
    Assert-True -Condition $Text.Contains($Expected) -Message $Message
}

function Assert-NotContains {
    param([string]$Text, [string]$Unexpected, [string]$Message)
    Assert-True -Condition (-not $Text.Contains($Unexpected)) -Message $Message
}

function Assert-Matches {
    param([string]$Text, [string]$Pattern, [string]$Message)
    Assert-True -Condition ([regex]::IsMatch($Text, $Pattern)) -Message $Message
}

function Get-SingleRegexGroup {
    param([string]$RelativePath, [string]$Pattern)
    $matches = [regex]::Matches((Get-Text $RelativePath), $Pattern)
    Assert-True -Condition ($matches.Count -eq 1) -Message "Expected one version match in $RelativePath; found $($matches.Count)."
    return $matches[0].Groups[1].Value
}

function Get-RookLockVersion {
    $content = Get-Text 'mcp_server/uv.lock'
    $blocks = [regex]::Matches($content, '(?ms)^\[\[package\]\]\r?\n(?<body>.*?)(?=^\[\[package\]\]|\z)')
    $rookBlocks = @($blocks | Where-Object {
        $_.Groups['body'].Value -match '(?m)^name = "rook-mcp"$'
    })
    Assert-True -Condition ($rookBlocks.Count -eq 1) -Message "Expected one rook-mcp package block; found $($rookBlocks.Count)."
    $versionMatch = [regex]::Match($rookBlocks[0].Groups['body'].Value, '(?m)^version = "([^"]+)"$')
    Assert-True -Condition $versionMatch.Success -Message 'rook-mcp package block has no version.'
    return $versionMatch.Groups[1].Value
}

function Get-LiteralPowerShellArray {
    param([string]$Text, [string]$VariableName)
    $pattern = '(?ms)\$' + [regex]::Escape($VariableName) + '\s*=\s*@\((?<body>.*?)\)'
    $arrayMatch = [regex]::Match($Text, $pattern)
    Assert-True -Condition $arrayMatch.Success -Message "Release workflow must declare `$${VariableName}."
    $body = $arrayMatch.Groups['body'].Value
    $itemMatches = [regex]::Matches($body, "'([^']+)'")
    $remainder = [regex]::Replace($body, "'[^']+'", '') -replace '[,\s]', ''
    Assert-True -Condition ($remainder.Length -eq 0) -Message "`$${VariableName} must contain only literal strings."
    return @($itemMatches | ForEach-Object { $_.Groups[1].Value })
}

function Test-Metadata {
    $expectedVersion = Get-SingleRegexGroup 'mcp_server/pyproject.toml' '(?m)^version = "([^"]+)"$'
    Assert-True -Condition ($expectedVersion -match '^[0-9]+\.[0-9]+\.[0-9]+$') -Message "pyproject version '$expectedVersion' is not SemVer X.Y.Z."

    $resource = Get-Text 'src/RookNative/RookNative.rc'
    $resourceVersion = Get-SingleRegexGroup 'src/RookNative/RookNative.rc' 'VALUE "FileVersion", "([0-9]+\.[0-9]+\.[0-9]+)\.0"'
    $versions = [ordered]@{
        uv_lock = Get-RookLockVersion
        installer = Get-SingleRegexGroup 'installer/RookSetup.iss' '(?m)^#define MyAppVersion "([^"]+)"$'
        companion = Get-SingleRegexGroup 'src/Rook/Rook.csproj' '<Version>([^<]+)</Version>'
        bim = Get-SingleRegexGroup 'src/RookBim/RookBim.csproj' '<Version>([^<]+)</Version>'
        native_resource = $resourceVersion
        native_plugin = Get-SingleRegexGroup 'src/RookNative/RookNativePlugin.cpp' 'm_plugin_version\(L"([^"]+)"\)'
        native_server = Get-SingleRegexGroup 'src/RookNative/RookServer.cpp' 'kRookNativePluginVersion = "([^"]+)"'
    }

    $plugin = Get-Text '.claude-plugin/plugin.json' | ConvertFrom-Json
    $marketplace = Get-Text '.claude-plugin/marketplace.json' | ConvertFrom-Json
    $versions['claude_plugin'] = $plugin.version
    $versions['claude_marketplace_metadata'] = $marketplace.metadata.version
    $versions['claude_marketplace_plugin'] = $marketplace.plugins[0].version

    foreach ($entry in $versions.GetEnumerator()) {
        Assert-True -Condition ($entry.Value -eq $expectedVersion) -Message "$($entry.Key) version '$($entry.Value)' must equal $expectedVersion."
    }

    $commaVersion = $expectedVersion -replace '\.', ','
    Assert-Matches -Text $resource -Pattern "(?m)^ FILEVERSION $([regex]::Escape($commaVersion)),0$" -Message 'Native FILEVERSION must match pyproject.'
    Assert-Matches -Text $resource -Pattern "(?m)^ PRODUCTVERSION $([regex]::Escape($commaVersion)),0$" -Message 'Native PRODUCTVERSION must match pyproject.'
    Assert-Contains -Text $resource -Expected "VALUE `"ProductVersion`", `"$expectedVersion.0`"" -Message 'Native ProductVersion string must match pyproject.'

    Assert-True -Condition ($plugin.skills -eq './.claude/skills/') -Message 'Claude plugin skills path must be plugin-root-relative.'
    # Claude Code loads the plugin's hooks/hooks.json automatically; a manifest 'hooks' entry pointing at it is
    # rejected as a duplicate ('Duplicate hooks file detected', Claude Code 2.1.x) and the whole plugin fails to load.
    Assert-True -Condition ($null -eq $plugin.PSObject.Properties['hooks']) -Message 'Claude plugin manifest must not declare hooks/hooks.json; Claude Code auto-loads it and rejects the duplicate.'
    Assert-True -Condition (Test-Path -LiteralPath (Join-Path $RepoRoot 'hooks\hooks.json') -PathType Leaf) -Message 'hooks/hooks.json must exist for auto-loading.'
    Assert-True -Condition ($plugin.repository -eq $PublicRepository) -Message 'Claude plugin repository must be public.'
    Assert-True -Condition ($marketplace.plugins[0].repository -eq $PublicRepository) -Message 'Marketplace plugin repository must be public.'

    $manifestDescriptions = "$($plugin.description)`n$($marketplace.metadata.description)`n$($marketplace.plugins[0].description)"
    foreach ($retiredClaim in @('RoadCreator', 'RookRoads', '3D road design', '3D roads')) {
        Assert-NotContains -Text $manifestDescriptions -Unexpected $retiredClaim -Message "Claude manifests must not advertise $retiredClaim."
    }

    $wheelhousePath = Get-RepoPath 'scripts/python-runtime/build-rook-python-wheelhouse.ps1'
    $tokens = $null
    $parseErrors = $null
    $wheelhouseAst = [System.Management.Automation.Language.Parser]::ParseFile($wheelhousePath, [ref]$tokens, [ref]$parseErrors)
    Assert-True -Condition ($parseErrors.Count -eq 0) -Message "Wheelhouse builder does not parse: $($parseErrors -join '; ')"
    $versionParameters = @($wheelhouseAst.ParamBlock.Parameters | Where-Object { $_.Name.VariablePath.UserPath -eq 'Version' })
    Assert-True -Condition ($versionParameters.Count -eq 1) -Message 'Wheelhouse builder must declare one Version parameter.'
    $versionParameter = $versionParameters[0]
    Assert-True -Condition ($null -eq $versionParameter.DefaultValue) -Message 'Wheelhouse Version must not have a default.'
    Assert-Matches -Text $versionParameter.Extent.Text -Pattern '(?s)Parameter\s*\(\s*Mandatory\s*=\s*\$true\s*\)' -Message 'Wheelhouse Version must be mandatory.'
    Assert-Contains -Text $versionParameter.Extent.Text -Expected 'ValidatePattern' -Message 'Wheelhouse Version must validate SemVer.'

    $native = Get-Text 'src/RookNative/RookNativePlugin.cpp'
    Assert-Contains -Text $native -Expected "RHINO_PLUG_IN_DEVELOPER_WEBSITE(L`"$PublicRepository`")" -Message 'Native website must be public.'
    Assert-Contains -Text $native -Expected "RHINO_PLUG_IN_UPDATE_URL(L`"$PublicReleases`")" -Message 'Native update URL must be public.'

    $assemblyInfo = Get-Text 'src/Rook/Properties/AssemblyInfo.cs'
    Assert-Contains -Text $assemblyInfo -Expected "DescriptionType.WebSite, `"$PublicRepository`"" -Message 'Companion website must be public.'

    foreach ($registrationScript in @('scripts/register-rooknative-suite.ps1', 'scripts/register-companion.ps1')) {
        $registration = Get-Text $registrationScript
        Assert-Contains -Text $registration -Expected "-Value '$PublicRepository'" -Message "$registrationScript website must be public."
        Assert-Contains -Text $registration -Expected "-Value '$PublicReleases'" -Message "$registrationScript update URL must be public."
        Assert-NotContains -Text $registration -Unexpected 'bringfire/Rhino_AI' -Message "$registrationScript retains the retired repository URL."
    }
}

function Test-Guidance {
    $guidanceFiles = @(
        'README.md',
        'CLAUDE.md',
        'QUICK_START.md',
        'AGENT_SETUP.md',
        'mcp_server/README.md',
        'installer/pre-install-readme.txt',
        'BUILDING.md'
    )
    $combined = ($guidanceFiles | ForEach-Object { Get-Text $_ }) -join "`n"

    foreach ($stalePhrase in @(
        'Python 3.10+ required for the Windows installer',
        'The installer requires Python 3.10+',
        'using your system Python',
        'nearly 400 tools',
        '~390 tools',
        '113 tools',
        'ONE atomic call',
        'one atomic write',
        'Modify the Grasshopper canvas atomically',
        'every operation outcome'
    )) {
        Assert-NotContains -Text $combined -Unexpected $stalePhrase -Message "Active guidance retains stale phrase: $stalePhrase"
    }

    Assert-NotContains -Text $combined -Unexpected 'https://github.com/bringfire/Rook/releases' -Message 'User-facing releases must use rook-release.'
    # Bug reports and contributions go to the public source repository (open source since 2026-09);
    # installer releases stay on rook-release, asserted above.

    $readme = Get-Text 'README.md'
    Assert-Contains -Text $readme -Expected 'https://github.com/bringfire/Rook/issues' -Message 'README support must point to the public source repository issues.'
    Assert-NotContains -Text $readme -Unexpected '**Rook requires [Claude Code]' -Message 'README must not require Claude Code.'
    Assert-Contains -Text $readme -Expected 'bundled CPython 3.11.9' -Message 'README must describe bundled Python.'
    Assert-Contains -Text $readme -Expected 'Codex skills' -Message 'README must describe installer-owned Codex skills.'
    Assert-Contains -Text $readme -Expected 'marketplace plugin' -Message 'README must describe Claude marketplace ownership.'

    $normativeEdit = 'One request, ordered non-transactional mutations, at most one post-mutation solve request—not an all-or-nothing transaction.'
    foreach ($agentFile in @('CLAUDE.md', 'AGENT_SETUP.md')) {
        $text = Get-Text $agentFile
        Assert-Contains -Text $text -Expected $normativeEdit -Message "$agentFile must contain the normative gh_edit contract."
        foreach ($requiredEvidence in @('partial_success', 'edit_summary', 'gh_snapshot', 'gh_errors')) {
            Assert-Contains -Text $text -Expected $requiredEvidence -Message "$agentFile must require $requiredEvidence verification."
        }
    }

    $mcpReadme = Get-Text 'mcp_server/README.md'
    Assert-NotContains -Text $mcpReadme -Unexpected 'enables Claude' -Message 'MCP README must be client-neutral.'
    Assert-NotContains -Text $mcpReadme -Unexpected 'requires an Anthropic API key' -Message 'MCP README must not require Anthropic.'
    Assert-Contains -Text $mcpReadme -Expected 'profile' -Message 'MCP README must describe profile admission.'

    Assert-NotContains -Text (Get-Text 'BUILDING.md') -Unexpected '..\RookRoads\RookRoads.csproj' -Message 'Supported build guidance must not build RookRoads.'
}

function Test-Workflow {
    $agentSkill = Get-RepoPath '.agents/skills/build-release/SKILL.md'
    $claudeSkill = Get-RepoPath '.claude/skills/build-release/SKILL.md'
    $agentReference = Get-RepoPath '.agents/skills/build-release/references/version-locations.md'
    $claudeReference = Get-RepoPath '.claude/skills/build-release/references/version-locations.md'

    Assert-True -Condition ([System.Linq.Enumerable]::SequenceEqual([byte[]][IO.File]::ReadAllBytes($agentSkill), [byte[]][IO.File]::ReadAllBytes($claudeSkill))) -Message 'Build-release SKILL.md mirrors differ.'
    Assert-True -Condition ([System.Linq.Enumerable]::SequenceEqual([byte[]][IO.File]::ReadAllBytes($agentReference), [byte[]][IO.File]::ReadAllBytes($claudeReference))) -Message 'Version-location mirrors differ.'

    $workflow = (Get-Content -LiteralPath $agentSkill -Raw) + "`n" + (Get-Content -LiteralPath $agentReference -Raw)
    Assert-Contains -Text $workflow -Expected '10 files / 14 edits' -Message 'Release workflow must own ten files and fourteen edits.'
    foreach ($versionPath in @(
        'mcp_server/pyproject.toml',
        'mcp_server/uv.lock',
        'installer/RookSetup.iss',
        'src/Rook/Rook.csproj',
        'src/RookBim/RookBim.csproj',
        'src/RookNative/RookNative.rc',
        'src/RookNative/RookNativePlugin.cpp',
        'src/RookNative/RookServer.cpp',
        '.claude-plugin/plugin.json',
        '.claude-plugin/marketplace.json'
    )) {
        Assert-Contains -Text $workflow -Expected $versionPath -Message "Release workflow omits $versionPath."
    }

    foreach ($requiredContract in @(
        'uv lock',
        'claude plugin validate --strict .',
        'scripts/tests/release-surface-hygiene.tests.ps1',
        'release-installer-guards.tests.ps1 -SkipBuiltPayloadCheck',
        'git worktree add --detach',
        'bringfire/rook-release',
        'Get-FileHash',
        'scripts/session-start.sh',
        'hooks/hooks.json',
        '.claude-plugin/plugin.json',
        '.claude-plugin/marketplace.json',
        'LICENSE'
    )) {
        Assert-Contains -Text $workflow -Expected $requiredContract -Message "Release workflow omits $requiredContract."
    }

    $expectedSkills = @('capture-convention', 'chirp', 'chirp-cascade', 'clean-layers', 'design-grasshopper', 'execute-grasshopper', 'plan-grasshopper', 'project-setup', 'twisted-column')
    $expectedSingletons = @('.claude-plugin/plugin.json', '.claude-plugin/marketplace.json', 'hooks/hooks.json', 'scripts/session-start.sh', 'LICENSE')
    $actualSkills = @(Get-LiteralPowerShellArray -Text $workflow -VariableName 'publicSkillNames')
    $actualSingletons = @(Get-LiteralPowerShellArray -Text $workflow -VariableName 'singletonPaths')
    Assert-True -Condition (($actualSkills -join "`n") -eq ($expectedSkills -join "`n")) -Message 'Public skill promotion inventory must equal the nine approved roots in order.'
    Assert-True -Condition (($actualSingletons -join "`n") -eq ($expectedSingletons -join "`n")) -Message 'Public singleton promotion inventory must equal the five self-contained paths in order.'

    Assert-Contains -Text $workflow -Expected 'gh -R bringfire/rook-release release create' -Message 'Release must be created explicitly in rook-release.'
    Assert-NotContains -Text $workflow -Unexpected "gh release create v`$Version" -Message 'Workflow must not create a release in the private repository.'
    Assert-Contains -Text $workflow -Expected 'Release-installer payload guard failed' -Message 'Release workflow must run the full installer guard after builds.'

    $hooks = Get-Text 'hooks/hooks.json' | ConvertFrom-Json
    $hookCommand = $hooks.hooks.SessionStart[0].hooks[0].command
    Assert-Contains -Text $hookCommand -Expected 'scripts/session-start.sh' -Message 'Hook manifest must execute the promoted session-start script.'
    Assert-True -Condition (Test-Path -LiteralPath (Get-RepoPath 'scripts/session-start.sh') -PathType Leaf) -Message 'Private session-start script is missing.'
    Assert-True -Condition (Test-Path -LiteralPath (Get-RepoPath 'LICENSE') -PathType Leaf) -Message 'Private LICENSE is missing.'

    $plugin = Get-Text '.claude-plugin/plugin.json' | ConvertFrom-Json
    $marketplace = Get-Text '.claude-plugin/marketplace.json' | ConvertFrom-Json
    Assert-True -Condition ($plugin.license -eq 'SEE LICENSE IN LICENSE') -Message 'Plugin manifest license pointer changed unexpectedly.'
    Assert-True -Condition ($marketplace.plugins[0].license -eq 'SEE LICENSE IN LICENSE') -Message 'Marketplace license pointer changed unexpectedly.'
}

$tests = [ordered]@{
    Metadata = ${function:Test-Metadata}
    Guidance = ${function:Test-Guidance}
    Workflow = ${function:Test-Workflow}
}

foreach ($entry in $tests.GetEnumerator()) {
    if ($Area -eq 'All' -or $Area -eq $entry.Key) {
        & $entry.Value
    }
}

Write-Host "Release surface hygiene tests passed ($Area)."
