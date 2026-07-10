param(
    [string]$GrasshopperDll = "C:\Program Files\Rhino 8\Plug-ins\Grasshopper\Grasshopper.dll",
    [string]$GrasshopperXml = "C:\Program Files\Rhino 8\Plug-ins\Grasshopper\Grasshopper.xml",
    [string]$RhinoCommonDll = "C:\Program Files\Rhino 8\System\RhinoCommon.dll"
)

if (-not (Test-Path -LiteralPath $GrasshopperDll)) { throw "Missing Grasshopper.dll: $GrasshopperDll" }
if (-not (Test-Path -LiteralPath $GrasshopperXml)) { throw "Missing Grasshopper.xml: $GrasshopperXml" }
if (-not (Test-Path -LiteralPath $RhinoCommonDll)) { throw "Missing RhinoCommon.dll: $RhinoCommonDll" }

[xml]$doc = Get-Content -Raw -LiteralPath $GrasshopperXml
$members = @($doc.doc.members.member)
$start = @($members | Where-Object { $_.name -eq "E:Grasshopper.Kernel.GH_Document.SolutionStart" })
$end = @($members | Where-Object { $_.name -eq "E:Grasshopper.Kernel.GH_Document.SolutionEnd" })
$schedule = @($members | Where-Object { $_.name -eq "M:Grasshopper.Kernel.GH_Document.ScheduleSolution(System.Int32)" })
$canvasChanged = @($members | Where-Object { $_.name -eq "E:Grasshopper.GUI.Canvas.GH_Canvas.DocumentChanged" })

if ($start.Count -ne 1 -or $end.Count -ne 1 -or $schedule.Count -ne 1 -or $canvasChanged.Count -ne 1) {
    throw "Installed Grasshopper lifecycle contract is incomplete."
}

[Reflection.Assembly]::LoadFrom($RhinoCommonDll) | Out-Null
$assembly = [Reflection.Assembly]::LoadFrom($GrasshopperDll)
$documentType = $assembly.GetType("Grasshopper.Kernel.GH_Document", $true)
$eventContracts = foreach ($name in "SolutionStart", "SolutionEnd") {
    $event = $documentType.GetEvent($name)
    $invoke = $event.EventHandlerType.GetMethod("Invoke")
    $parameters = $invoke.GetParameters()
    if ($invoke.ReturnType -ne [void] -or $parameters.Count -ne 2 -or
        -not [EventArgs].IsAssignableFrom($parameters[1].ParameterType) -or
        $parameters[1].ParameterType.GetProperty("Document") -eq $null) {
        throw "Unsupported $name delegate contract: $($event.EventHandlerType.FullName)"
    }

    [pscustomobject]@{
        name = $name
        delegate_type = $event.EventHandlerType.FullName
        invoke_signature = $invoke.ToString()
        event_args_document_type = $parameters[1].ParameterType.GetProperty("Document").PropertyType.FullName
    }
}

$canvasType = $assembly.GetType("Grasshopper.GUI.Canvas.GH_Canvas", $true)
$canvasEvent = $canvasType.GetEvent("DocumentChanged")
$canvasInvoke = $canvasEvent.EventHandlerType.GetMethod("Invoke")
$canvasParameters = $canvasInvoke.GetParameters()
$canvasArgs = $canvasParameters[1].ParameterType
if ($canvasInvoke.ReturnType -ne [void] -or $canvasParameters.Count -ne 2 -or
    -not [EventArgs].IsAssignableFrom($canvasArgs) -or
    $canvasArgs.GetProperty("OldDocument") -eq $null -or
    $canvasArgs.GetProperty("NewDocument") -eq $null) {
    throw "Unsupported DocumentChanged delegate contract: $($canvasEvent.EventHandlerType.FullName)"
}

[pscustomobject]@{
    solution_start_documented = $start[0].SelectSingleNode("summary").InnerText.Trim()
    solution_end_documented = $end[0].SelectSingleNode("summary").InnerText.Trim()
    schedule_solution_documented = $schedule[0].SelectSingleNode("summary").InnerText.Trim()
    grasshopper_dll = $GrasshopperDll
    lifecycle_events = $eventContracts
    canvas_document_changed = [pscustomobject]@{
        delegate_type = $canvasEvent.EventHandlerType.FullName
        invoke_signature = $canvasInvoke.ToString()
        old_document_type = $canvasArgs.GetProperty("OldDocument").PropertyType.FullName
        new_document_type = $canvasArgs.GetProperty("NewDocument").PropertyType.FullName
    }
} | ConvertTo-Json -Depth 3
