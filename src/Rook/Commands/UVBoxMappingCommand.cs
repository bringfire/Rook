using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Rhino;
using Rhino.Commands;
using Rhino.DocObjects;
using Rhino.Input;
using Rhino.Input.Custom;

namespace Rook.Commands
{
    public class UVBoxMappingCommand : Command
    {
        public override string EnglishName => "UVBoxMapping";

        protected override Result RunCommand(RhinoDoc doc, RunMode mode)
        {
            // Get default scale from document units
            var (defaultScale, unitsName) = GetDefaultScale(doc.ModelUnitSystem);
            RhinoApp.WriteLine($"Default scale: 1 UV unit = {defaultScale} {unitsName} (1 meter)");

            // Get selected objects
            var go = new GetObject();
            go.SetCommandPrompt("Select objects for box UV mapping");
            go.GeometryFilter = ObjectType.Surface | ObjectType.PolysrfFilter | ObjectType.Mesh;
            go.GetMultiple(1, 0);

            if (go.CommandResult() != Result.Success)
                return go.CommandResult();

            // Ask for scale
            var getNumber = new GetNumber();
            getNumber.SetCommandPrompt($"UV scale ({unitsName} per UV unit, Enter for default)");
            getNumber.SetDefaultNumber(defaultScale);

            var getResult = getNumber.Get();
            double targetScale = defaultScale;

            if (getResult == GetResult.Number)
                targetScale = getNumber.Number();
            else if (getResult != GetResult.Nothing)
                return Result.Cancel;

            if (targetScale <= 0)
            {
                RhinoApp.WriteLine("Scale must be positive");
                return Result.Failure;
            }

            // Build JSON body and call handler
            var ids = go.Objects().Select(o => o.ObjectId.ToString()).ToList();
            var request = new Dictionary<string, object>
            {
                ["ids"] = ids,
                ["scale"] = targetScale
            };

            var body = JsonSerializer.Serialize(request);
            var handler = new Handlers.TextureMappingHandler();
            var response = handler.ApplyBoxMapping(body);

            if (response.Success)
            {
                var data = response.Data as Dictionary<string, object>;
                var mappedCount = data != null && data.ContainsKey("mapped_count") ? data["mapped_count"] : 0;
                RhinoApp.WriteLine($"Box UV mapping applied to {mappedCount}/{ids.Count} objects (scale: {targetScale} {unitsName})");
            }
            else
            {
                RhinoApp.WriteLine($"UV mapping failed: {response.Data}");
                return Result.Failure;
            }

            return Result.Success;
        }

        private static (double scale, string name) GetDefaultScale(UnitSystem units)
        {
            switch (units)
            {
                case UnitSystem.Millimeters: return (1000.0, "mm");
                case UnitSystem.Centimeters: return (100.0, "cm");
                case UnitSystem.Meters: return (1.0, "m");
                case UnitSystem.Inches: return (39.37, "in");
                case UnitSystem.Feet: return (3.28, "ft");
                case UnitSystem.Yards: return (0.328, "yd");
                default: return (1000.0, "units");
            }
        }
    }
}
