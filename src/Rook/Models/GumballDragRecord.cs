using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Rook.Models
{
    /// <summary>
    /// Which gumball handle was dragged. Maps to Rhino.UI.Gumball.GumballMode.
    /// </summary>
    [JsonConverter(typeof(JsonStringEnumConverter))]
    public enum GumballHandleMode
    {
        None,
        TranslateX,
        TranslateY,
        TranslateZ,
        TranslateXY,
        TranslateYZ,
        TranslateZX,
        RotateX,
        RotateY,
        RotateZ,
        ScaleX,
        ScaleY,
        ScaleZ,
        ScaleXY,
        ScaleYZ,
        ScaleZX,
        TranslateFree,
        ExtrudeX,
        ExtrudeY,
        ExtrudeZ,
        CutX,
        CutY,
        CutZ,
        Menu
    }

    /// <summary>
    /// Records a single gumball drag operation with full transform fidelity.
    /// Each time the user completes a drag (mouse up after picking a handle),
    /// one GumballDragRecord is created.
    /// </summary>
    public class GumballDragRecord
    {
        /// <summary>
        /// Sequence number within the AIGumball session (1-based).
        /// </summary>
        public int DragIndex { get; set; }

        /// <summary>
        /// Which handle was dragged (e.g., TranslateX, RotateZ, ScaleXY).
        /// </summary>
        public GumballHandleMode HandleMode { get; set; }

        /// <summary>
        /// The transform delta for THIS drag only (GumballTransform from the conduit).
        /// 4x4 matrix stored as 16 doubles in row-major order.
        /// </summary>
        public double[]? DeltaTransformMatrix { get; set; }

        /// <summary>
        /// The cumulative transform up to and including this drag (TotalTransform).
        /// 4x4 matrix stored as 16 doubles in row-major order.
        /// </summary>
        public double[]? CumulativeTransformMatrix { get; set; }

        /// <summary>
        /// Whether this drag was a copy operation (user held Alt).
        /// </summary>
        public bool IsCopy { get; set; }

        /// <summary>
        /// Whether the user was relocating the gumball itself (Ctrl-click drag).
        /// Relocate drags don't transform geometry — they reposition the gumball widget.
        /// </summary>
        public bool IsRelocate { get; set; }

        /// <summary>
        /// When this drag completed (mouse up).
        /// </summary>
        public DateTime Timestamp { get; set; } = DateTime.UtcNow;

        /// <summary>
        /// Duration of the drag from mouse down to mouse up, in milliseconds.
        /// </summary>
        public double DragDurationMs { get; set; }

        // --- Numeric input / drag settings ---

        /// <summary>
        /// Whether this drag was a numeric input (user clicked handle without dragging, then typed a value).
        /// </summary>
        public bool IsNumericInput { get; set; }

        /// <summary>
        /// The typed numeric value (only set when IsNumericInput is true).
        /// </summary>
        public double? NumericValue { get; set; }

        /// <summary>
        /// Drag strength multiplier that was active during this drag.
        /// </summary>
        public double DragStrength { get; set; } = 1.0;

        // --- Extrude/Cut fields (only populated for extrude/cut drags) ---

        /// <summary>
        /// Distance extruded along the axis (positive = outward/extrude, negative = inward/cut).
        /// </summary>
        public double? ExtrudeDistance { get; set; }

        /// <summary>
        /// Whether the extrusion was capped.
        /// </summary>
        public bool? ExtrudeCapped { get; set; }

        /// <summary>
        /// What kind of geometry was extruded: "face", "curve", "solid", "subd".
        /// </summary>
        public string? ExtrudeGeometryType { get; set; }

        /// <summary>
        /// Boolean operation performed: "union", "difference", or "none".
        /// </summary>
        public string? BooleanOperation { get; set; }

        /// <summary>
        /// GUIDs of objects created by this drag (e.g., copies, extrusion results).
        /// </summary>
        public List<string>? ObjectsCreated { get; set; }

        /// <summary>
        /// GUIDs of objects deleted by this drag (e.g., originals replaced by boolean result).
        /// </summary>
        public List<string>? ObjectsDeleted { get; set; }
    }
}
