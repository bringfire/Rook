using System;
using System.Collections.Generic;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Architecture;

namespace RookBim.Revit
{
    /// <summary>
    /// Exports rooms/spaces as typed spatial-structure REFERENCE geometry on a dedicated layer.
    /// Degrades per room: room_volume_brep -> room_mesh -> boundary_2d -> label_only. A room whose
    /// volume cannot be extracted is NOT an export failure as long as its label record is emitted.
    /// Read-only.
    /// </summary>
    internal sealed class RevitRoomExporter
    {
        public const string RoomsLayer = "RookBim::Rooms";

        public const string RepVolumeBrep = "room_volume_brep";
        public const string RepMesh = "room_mesh";
        public const string RepBoundary2d = "boundary_2d";
        public const string RepLabelOnly = "label_only";

        // JSON wire-format key used in sidecar records to flag this as non-element reference geometry.
        public const string SidecarKeyReferenceGeometry = "referenceGeometry";

        private readonly double unitScaleFromFeet;

        public RevitRoomExporter(double unitScaleFromFeet)
        {
            this.unitScaleFromFeet = unitScaleFromFeet;
        }

        public IReadOnlyList<RevitRoomExport> ExportRooms(Document document)
        {
            var results = new List<RevitRoomExport>();
            var collector = new FilteredElementCollector(document)
                .OfClass(typeof(SpatialElement))
                .WhereElementIsNotElementType();

            foreach (var element in collector)
            {
                if (element is Room room)
                {
                    results.Add(ExportRoom(room));
                }
            }

            return results;
        }

        private RevitRoomExport ExportRoom(Room room)
        {
            var export = new RevitRoomExport
            {
                UniqueId = room.UniqueId,
                Number = room.Number,
                Name = room.Name,
                Representation = RepLabelOnly,
                ReferenceGeometry = true
            };

            try
            {
                var options = new SpatialElementBoundaryOptions();
                var calculator = new SpatialElementGeometryCalculator(room.Document, options);
                var solidResult = calculator.CalculateSpatialElementGeometry(room);
                var solid = solidResult?.GetGeometry();
                if (solid != null && solid.Volume > 0)
                {
                    export.Solid = solid;
                    export.Representation = RepMesh; // assembled to mesh/brep in the export service
                    return export;
                }
            }
            catch (Exception)
            {
                // fall through to boundary / label-only
            }

            if (TryBoundaryLoops(room))
            {
                export.Representation = RepBoundary2d;
            }

            return export;
        }

        private bool TryBoundaryLoops(Room room)
        {
            try
            {
                var loops = room.GetBoundarySegments(new SpatialElementBoundaryOptions());
                return loops != null && loops.Count > 0;
            }
            catch (Exception)
            {
                return false;
            }
        }
    }

    internal sealed class RevitRoomExport
    {
        public string UniqueId { get; set; } = string.Empty;

        public string? Number { get; set; }

        public string? Name { get; set; }

        public string Representation { get; set; } = RevitRoomExporter.RepLabelOnly;

        public bool ReferenceGeometry { get; set; } = true;

        public Solid? Solid { get; set; }
    }
}
