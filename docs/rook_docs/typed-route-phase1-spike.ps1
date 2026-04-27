param(
    [string]$OutFile = "c:\Users\aryan\source\repos\rook_docs\typed-route-phase1-spike-report.json"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-RookBaseUrl {
    $dir = Join-Path $env:TEMP "rook"
    if (-not (Test-Path $dir)) {
        throw "Rook discovery directory not found: $dir"
    }

    $instance = Get-ChildItem $dir -Filter "instance-*-native.json" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if (-not $instance) {
        throw "No native discovery file found in $dir"
    }

    $json = Get-Content $instance.FullName -Raw | ConvertFrom-Json
    if (-not $json.port) {
        throw "Discovery file missing port: $($instance.FullName)"
    }

    return "http://127.0.0.1:$($json.port)"
}

function Invoke-Rook {
    param(
        [ValidateSet("GET", "POST", "DELETE")]
        [string]$Method,
        [string]$Path,
        [object]$Body = $null,
        [int]$TimeoutSec = 100
    )

    $uri = "$script:BaseUrl$Path"
    if ($Method -eq "GET") {
        return Invoke-RestMethod -Method Get -Uri $uri -ContentType "application/json" -TimeoutSec $TimeoutSec
    }

    $payload = if ($null -eq $Body) { "{}" } else { ($Body | ConvertTo-Json -Depth 8 -Compress) }
    return Invoke-RestMethod -Method $Method -Uri $uri -Body $payload -ContentType "application/json" -TimeoutSec $TimeoutSec
}

function Assert-Success {
    param(
        [string]$Label,
        [object]$Response
    )

    if (-not $Response.success) {
        throw "$Label failed: $($Response.data | ConvertTo-Json -Depth 8 -Compress)"
    }
}

function New-ObjectIdMap {
    return [ordered]@{}
}

function Add-CreatedObject {
    param(
        $Map,
        [string]$Key,
        [object]$Response
    )

    Assert-Success $Key $Response
    $Map[$Key] = $Response.data.id
}

function Invoke-CommandProbe {
    param(
        [string]$Name,
        [string]$Command,
        [string]$Provenance,
        [hashtable]$ProposedData,
        [int]$TimeoutSec = 15
    )

    Write-Host "  probe: $Name ..." -NoNewline

    $probeStart = Get-Date
    $response = $null
    $probeError = $null

    try {
        $response = Invoke-Rook -Method POST -Path "/command" -Body @{
            command = $Command
            echo = $false
        } -TimeoutSec $TimeoutSec
    }
    catch {
        $probeError = $_.Exception.Message
    }

    $elapsedMs = [int]((Get-Date) - $probeStart).TotalMilliseconds
    if ($probeError) {
        Write-Host " ERROR/TIMEOUT (${elapsedMs}ms)" -ForegroundColor Yellow
    } elseif ($response.success -and $response.data.objectsCreated -gt 0) {
        Write-Host " ok (${elapsedMs}ms, $($response.data.objectsCreated) created)" -ForegroundColor Green
    } elseif ($response.success) {
        Write-Host " no-op (${elapsedMs}ms, executed=$($response.data.executed), 0 objects)" -ForegroundColor Yellow
    } else {
        Write-Host " stalled/failed (${elapsedMs}ms)" -ForegroundColor Yellow
    }

    return [ordered]@{
        name = $Name
        provenance = $Provenance
        command = $Command
        currentResponse = $response
        probeError = $probeError
        elapsedMs = $elapsedMs
        currentDataSummary = if ($null -ne $response -and $response.success) {
            "command, executed, objectsCreated, objectIds"
        } elseif ($null -ne $response) {
            "command, executed=false, error, waitingFor, objectsCreated, objectIds"
        } else {
            "no response (timeout or error)"
        }
        proposedTypedData = $ProposedData
    }
}

$script:BaseUrl = Get-RookBaseUrl

$objects = New-ObjectIdMap
$report = [ordered]@{
    generatedAt = (Get-Date).ToString("s")
    baseUrl = $script:BaseUrl
    setup = [ordered]@{}
    probes = @()
}

# -------------------------------------------------------------------
# Setup geometry: all created through existing typed routes for repeatability
# -------------------------------------------------------------------

# Loft profiles
Add-CreatedObject $objects "loft_circle_1" (Invoke-Rook POST "/create" @{
    type = "CIRCLE"; center = @(0, 100, 0); radius = 10; name = "Spike_LoftCircle1"
})
Add-CreatedObject $objects "loft_circle_2" (Invoke-Rook POST "/create" @{
    type = "CIRCLE"; center = @(0, 100, 15); radius = 6; name = "Spike_LoftCircle2"
})
Add-CreatedObject $objects "loft_circle_3" (Invoke-Rook POST "/create" @{
    type = "CIRCLE"; center = @(0, 100, 30); radius = 8; name = "Spike_LoftCircle3"
})

# Sweep1 setup: one rail + one open profile at the rail start
Add-CreatedObject $objects "sweep1_rail" (Invoke-Rook POST "/create" @{
    type = "LINE"; start = @(100, 0, 0); end = @(100, 0, 30); name = "Spike_Sweep1Rail"
})
Add-CreatedObject $objects "sweep1_profile" (Invoke-Rook POST "/create" @{
    type = "LINE"; start = @(98, 0, 0); end = @(102, 0, 0); name = "Spike_Sweep1Profile"
})

# Sweep2 setup: two rails + one cross-section
Add-CreatedObject $objects "sweep2_rail_1" (Invoke-Rook POST "/create" @{
    type = "LINE"; start = @(130, -5, 0); end = @(130, -5, 30); name = "Spike_Sweep2Rail1"
})
Add-CreatedObject $objects "sweep2_rail_2" (Invoke-Rook POST "/create" @{
    type = "LINE"; start = @(130, 5, 0); end = @(130, 5, 30); name = "Spike_Sweep2Rail2"
})
Add-CreatedObject $objects "sweep2_section" (Invoke-Rook POST "/create" @{
    type = "LINE"; start = @(130, -5, 0); end = @(130, 5, 0); name = "Spike_Sweep2Section"
})

# Pipe rail
Add-CreatedObject $objects "pipe_rail" (Invoke-Rook POST "/create" @{
    type = "LINE"; start = @(160, 0, 0); end = @(160, 0, 30); name = "Spike_PipeRail"
})

# Revolve profile (parallel to axis; should create a cylindrical-like revolve if scripted cleanly)
Add-CreatedObject $objects "revolve_profile" (Invoke-Rook POST "/create" @{
    type = "LINE"; start = @(195, 0, 0); end = @(195, 0, 20); name = "Spike_RevolveProfile"
})

# Array seed object
Add-CreatedObject $objects "array_box" (Invoke-Rook POST "/create" @{
    type = "BOX"; origin = @(220, 0, 0); width = 2; depth = 2; height = 2; name = "Spike_ArrayBox"
})

$report.setup = $objects

# -------------------------------------------------------------------
# Probes
# -------------------------------------------------------------------

$report.probes += Invoke-CommandProbe -Name "Loft" -Provenance "repo-backed" `
    -Command "_-Loft _SelId $($objects['loft_circle_1']) _SelId $($objects['loft_circle_2']) _SelId $($objects['loft_circle_3']) _Enter" `
    -ProposedData @{
        class = "creator"
        fields = @("id", "type", "layer", "name", "visible", "color", "bbox")
    }

$report.probes += Invoke-CommandProbe -Name "Sweep1" -Provenance "docs-derived" `
    -Command "_-Sweep1 _SelId $($objects['sweep1_rail']) _Enter _SelId $($objects['sweep1_profile']) _Enter" `
    -ProposedData @{
        class = "creator"
        fields = @("id", "type", "layer", "name", "visible", "color", "bbox")
    }

$report.probes += Invoke-CommandProbe -Name "Sweep2" -Provenance "docs-derived" `
    -Command "_-Sweep2 _SelId $($objects['sweep2_rail_1']) _SelId $($objects['sweep2_rail_2']) _Enter _SelId $($objects['sweep2_section']) _Enter" `
    -ProposedData @{
        class = "creator"
        fields = @("id", "type", "layer", "name", "visible", "color", "bbox")
    }

$report.probes += Invoke-CommandProbe -Name "Pipe" -Provenance "docs-derived" `
    -Command "_-Pipe _SelId $($objects['pipe_rail']) _Enter 2 2 _Enter" `
    -ProposedData @{
        class = "creator"
        fields = @("id", "type", "layer", "name", "visible", "color", "bbox")
        notes = "Proposed typed route should also return cap/radius metadata if included in contract"
    }

$report.probes += Invoke-CommandProbe -Name "Revolve" -Provenance "docs-derived" `
    -Command "_-Revolve _SelId $($objects['revolve_profile']) _Enter 190,0,0 190,0,20 _FullCircle=_Yes _Enter" `
    -ProposedData @{
        class = "creator"
        fields = @("id", "type", "layer", "name", "visible", "color", "bbox")
    }

$report.probes += Invoke-CommandProbe -Name "ArrayRectangular" -Provenance "repo-backed" `
    -Command "_-Array _SelId $($objects['array_box']) _Enter _Rectangular 3 2 1 10 5 0" `
    -ProposedData @{
        class = "mutation"
        fields = @("createdCount", "ids", "mode", "xCount", "yCount", "zCount", "xSpacing", "ySpacing", "zSpacing")
    }

$report.probes += Invoke-CommandProbe -Name "ArrayLinear" -Provenance "docs-derived" `
    -Command "_-ArrayLinear _SelId $($objects['array_box']) _Enter 220,0,0 230,0,0 _Number=4 _Enter" `
    -ProposedData @{
        class = "mutation"
        fields = @("createdCount", "ids", "mode", "count", "direction", "distance")
    }

$report.probes += Invoke-CommandProbe -Name "ArrayPolar" -Provenance "docs-derived" `
    -Command "_-ArrayPolar _SelId $($objects['array_box']) _Enter 220,0,0 6 360 _Enter" `
    -ProposedData @{
        class = "mutation"
        fields = @("createdCount", "ids", "mode", "center", "axis", "count", "angle")
    }

$outDir = Split-Path -Parent $OutFile
if ($outDir -and -not (Test-Path $outDir)) {
    New-Item -ItemType Directory -Path $outDir | Out-Null
}

$report | ConvertTo-Json -Depth 8 | Set-Content -Path $OutFile -Encoding UTF8
Write-Host ""
Write-Host "Phase 1 spike report written to $OutFile"

$errored = $report.probes | Where-Object { $_.probeError }
if ($errored) {
    Write-Host ""
    Write-Warning "Some probes errored or timed out:"
    foreach ($p in $errored) {
        Write-Host "  - $($p.name): $($p.probeError)"
    }
    Write-Host ""
    Write-Host "If Rhino still has a pending command prompt, press Escape to clear it before re-running."
}
