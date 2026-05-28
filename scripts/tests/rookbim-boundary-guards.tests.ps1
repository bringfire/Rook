$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $repoRoot

function Fail($message) {
    Write-Error $message
    exit 1
}

$coreFiles = Get-ChildItem -Path "src/Rook" -Recurse -Include *.cs,*.csproj,*.props,*.targets -File
$coreRevitMatches = $coreFiles | Select-String -Pattern "Autodesk\.Revit|RevitAPI|RevitAPIUI" -CaseSensitive:$false
if ($coreRevitMatches) {
    $formatted = $coreRevitMatches | ForEach-Object { "$($_.Path):$($_.LineNumber): $($_.Line.Trim())" }
    Fail "src/Rook must not reference Revit APIs:`n$($formatted -join "`n")"
}

$nativeProjectFiles = @(
    "src/RookNative/RookNative.vcxproj",
    "src/RookNative/RookNative.vcxproj.filters"
)
foreach ($path in $nativeProjectFiles) {
    $nativeBimMatches = Select-String -Path $path -Pattern "bim" -CaseSensitive:$false
    if ($nativeBimMatches) {
        $formatted = $nativeBimMatches | ForEach-Object { "$($_.Path):$($_.LineNumber): $($_.Line.Trim())" }
        Fail "$path must not gain BIM project-file entries; keep Phase 1 native BIM routing in RookServer.cpp or explicitly approve project-file churn:`n$($formatted -join "`n")"
    }
}

$routeLines = Get-Content "src/RookNative/RookServer.cpp"
$badRoutes = for ($index = 0; $index -lt $routeLines.Count; $index++) {
    # Boundary tripwire only: catch obvious forbidden public route literals, not every possible C++ route-construction pattern.
    $normalized = $routeLines[$index] -replace "\\+/", "/"
    if ($normalized -match '["(]\^?/(?:revit|rookbim)(?=$|[^A-Za-z0-9_-])|["(]\^?/rhino/bim(?=$|[^A-Za-z0-9_-])') {
        [pscustomobject]@{
            Path = (Resolve-Path "src/RookNative/RookServer.cpp").Path
            LineNumber = $index + 1
            Line = $routeLines[$index]
        }
    }
}
if ($badRoutes) {
    $formatted = $badRoutes | ForEach-Object { "$($_.Path):$($_.LineNumber): $($_.Line.Trim())" }
    Fail "BIM public routes must use /bim/* only:`n$($formatted -join "`n")"
}

Write-Host "rookbim boundary guards passed"
