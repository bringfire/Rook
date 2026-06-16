using System;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Architecture;
using Autodesk.Revit.DB.Mechanical;

namespace RookBim.Revit
{
    /// <summary>Extracts provenance-tagged semantic labels for an element (read-only).</summary>
    internal sealed class RevitLabelExtractor
    {
        public RevitElementLabels Extract(Document document, Element element)
        {
            return new RevitElementLabels
            {
                Level = ExtractLevel(document, element),
                HostId = ExtractHost(document, element),
                ContainingRoom = ExtractRoom(element),
                ContainingSpace = ExtractSpace(element)
            };
        }

        private static BimSemanticLabel ExtractLevel(Document document, Element element)
        {
            var levelId = element.LevelId;
            if (levelId != null && levelId != ElementId.InvalidElementId)
            {
                var level = document.GetElement(levelId) as Level;
                if (level != null)
                {
                    return BimSemanticLabel.Present(level.Name, "revit_api", "high");
                }
            }

            var param = element.get_Parameter(BuiltInParameter.SCHEDULE_LEVEL_PARAM)
                ?? element.get_Parameter(BuiltInParameter.FAMILY_LEVEL_PARAM);
            var valueString = param?.AsValueString();
            if (!string.IsNullOrWhiteSpace(valueString))
            {
                return BimSemanticLabel.Present(valueString!, "parameter", "medium");
            }

            return BimSemanticLabel.Missing("no_level_association");
        }

        private static BimSemanticLabel ExtractHost(Document document, Element element)
        {
            if (element is FamilyInstance instance && instance.Host != null)
            {
                return BimSemanticLabel.Present(instance.Host.UniqueId, "revit_api", "high");
            }

            return BimSemanticLabel.Missing("element_is_not_hosted");
        }

        private static BimSemanticLabel ExtractRoom(Element element)
        {
            try
            {
                if (element is FamilyInstance instance)
                {
                    var room = instance.Room;
                    if (room != null)
                    {
                        return BimSemanticLabel.Present(room.UniqueId, "revit_api", "high");
                    }
                }
            }
            catch (Exception)
            {
                return BimSemanticLabel.Missing("room_lookup_unavailable");
            }

            return BimSemanticLabel.Missing("no_room_association");
        }

        private static BimSemanticLabel ExtractSpace(Element element)
        {
            try
            {
                if (element is FamilyInstance instance)
                {
                    var space = instance.Space;
                    if (space != null)
                    {
                        return BimSemanticLabel.Present(space.UniqueId, "revit_api", "high");
                    }
                }
            }
            catch (Exception)
            {
                return BimSemanticLabel.Missing("space_lookup_unavailable");
            }

            return BimSemanticLabel.Missing("no_space_association");
        }
    }

    internal sealed class RevitElementLabels
    {
        public BimSemanticLabel Level { get; set; } = BimSemanticLabel.Missing("not_extracted");

        public BimSemanticLabel HostId { get; set; } = BimSemanticLabel.Missing("not_extracted");

        public BimSemanticLabel ContainingRoom { get; set; } = BimSemanticLabel.Missing("not_extracted");

        public BimSemanticLabel ContainingSpace { get; set; } = BimSemanticLabel.Missing("not_extracted");
    }

    /// <summary>
    /// A label that is honest about provenance and absence.
    ///
    /// JSON shape: { value, source, confidence, missingReason }
    ///
    /// Source values:
    ///   "revit_api"   — read directly from the Revit element object model (e.g. element.LevelId).
    ///   "parameter"   — read from a built-in or shared Revit parameter (e.g. SCHEDULE_LEVEL_PARAM).
    ///   "derived"     — inferred from related elements or geometry when a direct source is absent.
    ///   "unavailable" — the label could not be determined from any available source.
    /// </summary>
    internal sealed class BimSemanticLabel
    {
        // Backing fields use camelCase names to match the JSON contract shape:
        //   { value, source, confidence, missingReason }
#pragma warning disable IDE1006 // Naming Styles — intentional camelCase for JSON contract
        public string? value { get; private set; }

        public string source { get; private set; } = "unavailable";

        public string? confidence { get; private set; }

        public string? missingReason { get; private set; }
#pragma warning restore IDE1006

        public static BimSemanticLabel Present(string labelValue, string labelSource, string labelConfidence)
        {
            return new BimSemanticLabel
            {
                value = labelValue,
                source = labelSource,
                confidence = labelConfidence,
                missingReason = null
            };
        }

        public static BimSemanticLabel Missing(string reason)
        {
            return new BimSemanticLabel
            {
                value = null,
                source = "unavailable",
                confidence = null,
                missingReason = reason
            };
        }
    }
}
