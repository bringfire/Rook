using System;
using System.Collections.Generic;
using System.Linq;
using Rhino;
using Rhino.DocObjects;
using Rhino.Geometry;

namespace Rook.Handlers
{
    /// <summary>
    /// Result of a gumball extrude/cut/boss operation.
    /// </summary>
    public class ExtrudeResult
    {
        public bool Success { get; set; }
        public string? Error { get; set; }
        public List<Guid> CreatedIds { get; set; } = new List<Guid>();
        public List<Guid> DeletedIds { get; set; } = new List<Guid>();
        public string GeometryType { get; set; } = "";
        public string? BooleanOperation { get; set; }
    }

    /// <summary>
    /// Geometry operations for gumball extrude, cut, and boss.
    /// Separated from AIGumballCommand to keep mouse handling focused.
    /// </summary>
    public static class GumballExtrudeHandler
    {
        /// <summary>
        /// Extrude a Brep face along a direction by a distance.
        /// Creates extrusion tool from face boundary → boolean union with original → single solid.
        /// </summary>
        public static ExtrudeResult ExtrudeFace(RhinoDoc doc, Guid objectId, int faceIndex,
                                                 Vector3d direction, double distance, bool cap = true)
        {
            var result = new ExtrudeResult { GeometryType = "face" };
            var rhinoObj = doc.Objects.FindId(objectId);
            if (rhinoObj?.Geometry is not Brep brep)
            {
                result.Error = "Object is not a Brep";
                return result;
            }

            if (faceIndex < 0 || faceIndex >= brep.Faces.Count)
            {
                result.Error = $"Face index {faceIndex} out of range (0-{brep.Faces.Count - 1})";
                return result;
            }

            var face = brep.Faces[faceIndex];
            var faceBrep = face.DuplicateFace(false);
            if (faceBrep == null)
            {
                result.Error = "Failed to duplicate face";
                return result;
            }

            // Get the outer loop as a curve for extrusion
            var outerLoop = faceBrep.Faces[0].OuterLoop;
            var curve = outerLoop?.To3dCurve();
            if (curve == null)
            {
                result.Error = "Failed to extract face boundary curve";
                return result;
            }

            var tolerance = doc.ModelAbsoluteTolerance;
            var unitDir = direction;
            unitDir.Unitize();
            var extrudeDir = unitDir * distance;

            // Nudge the extrusion start slightly INTO the original solid to prevent
            // coincident-face failures with boolean union. The shared face at the
            // extrusion base causes degenerate intersections — a small overlap gives
            // the boolean algorithm clean geometry to work with.
            var overlapAmount = Math.Max(tolerance * 10, Math.Abs(distance) * 0.005);
            var overlapVec = unitDir * Math.Sign(distance) * overlapAmount;
            var offsetCurve = curve.DuplicateCurve();
            offsetCurve.Translate(-overlapVec);
            var totalExtrudeVec = extrudeDir + overlapVec;

            var surface = Surface.CreateExtrusion(offsetCurve, totalExtrudeVec);
            if (surface == null)
            {
                result.Error = "Failed to create extrusion surface";
                return result;
            }

            var extrudedBrep = surface.ToBrep();
            if (extrudedBrep == null)
            {
                result.Error = "Failed to convert extrusion to Brep";
                return result;
            }

            if (cap && curve.IsClosed)
                extrudedBrep = extrudedBrep.CapPlanarHoles(tolerance) ?? extrudedBrep;

            // Boolean union with original to create extended solid
            RhinoApp.WriteLine($"ExtrudeFace: brep solid={brep.IsSolid}, extrusion solid={extrudedBrep.IsSolid}, overlap={overlapAmount:F4}");
            var union = Brep.CreateBooleanUnion(new[] { brep.DuplicateBrep(), extrudedBrep }, tolerance);
            RhinoApp.WriteLine($"ExtrudeFace: union result={(union != null ? union.Length.ToString() + " breps" : "null")}");
            if (union != null && union.Length > 0)
            {
                // Merge coplanar faces for cleaner geometry
                union[0].MergeCoplanarFaces(tolerance);
                RhinoApp.WriteLine($"ExtrudeFace: union[0] solid={union[0].IsSolid}, faces={union[0].Faces.Count}, volume={(union[0].IsSolid ? union[0].GetVolume():0):F2}");

                // Replace original with union result
                var newId = doc.Objects.Add(union[0], rhinoObj.Attributes);
                if (newId != Guid.Empty)
                {
                    doc.Objects.Delete(objectId, true);
                    result.CreatedIds.Add(newId);
                    result.DeletedIds.Add(objectId);
                    result.BooleanOperation = "union";
                    result.Success = true;
                }
                else
                    result.Error = "Failed to add union result to document";
            }
            else
            {
                // Boolean union failed — DO NOT delete original, just report error
                result.Error = "Boolean union failed — faces may not be planar or solid";
                RhinoApp.WriteLine($"ExtrudeFace: boolean union FAILED, original preserved");
            }

            return result;
        }

        /// <summary>
        /// Extrude a Brep face by decomposing the solid, creating wall surfaces,
        /// and rejoining — NO boolean union (avoids coincident-face failures).
        /// Algorithm:
        ///   1. Extract all faces EXCEPT the target → open shell
        ///   2. Create ruled wall surfaces from each edge of the target face
        ///   3. Create the translated copy of the target face
        ///   4. JoinBreps(shell + walls + translated face) → closed solid
        /// </summary>
        public static ExtrudeResult ExtrudeFaceDirect(RhinoDoc doc, Guid objectId, int faceIndex,
                                                       Vector3d direction, double distance)
        {
            var result = new ExtrudeResult { GeometryType = "face", BooleanOperation = "join" };
            var rhinoObj = doc.Objects.FindId(objectId);
            if (rhinoObj?.Geometry is not Brep brep || !brep.IsSolid)
            {
                result.Error = "Object is not a solid Brep";
                return result;
            }

            if (faceIndex < 0 || faceIndex >= brep.Faces.Count)
            {
                result.Error = $"Face index {faceIndex} out of range (0-{brep.Faces.Count - 1})";
                return result;
            }

            var tolerance = doc.ModelAbsoluteTolerance;
            var unitDir = direction;
            unitDir.Unitize();
            var extrudeVec = unitDir * distance;

            var face = brep.Faces[faceIndex];

            // Step 1: Extract all faces EXCEPT the target (creates an open shell)
            var shellPieces = new List<Brep>();
            for (int i = 0; i < brep.Faces.Count; i++)
            {
                if (i != faceIndex)
                    shellPieces.Add(brep.Faces[i].DuplicateFace(false));
            }

            // Step 2: Create wall surfaces from each edge of the target face
            var walls = new List<Brep>();
            var edgeIndices = new HashSet<int>();
            foreach (var loop in face.Loops)
            {
                foreach (var trim in loop.Trims)
                {
                    if (trim.Edge != null)
                        edgeIndices.Add(trim.Edge.EdgeIndex);
                }
            }

            foreach (var ei in edgeIndices)
            {
                var edge = brep.Edges[ei];
                var edgeCurve = edge.DuplicateCurve();
                var translatedCurve = edgeCurve.DuplicateCurve();
                translatedCurve.Translate(extrudeVec);

                // Ruled surface between original edge and translated edge
                var wallBreps = Brep.CreateFromLoft(
                    new[] { edgeCurve, translatedCurve },
                    Point3d.Unset, Point3d.Unset,
                    LoftType.Straight, false);

                if (wallBreps != null)
                    walls.AddRange(wallBreps);
            }

            // Step 3: Create the translated face
            var newFaceBrep = face.DuplicateFace(false);
            newFaceBrep.Translate(extrudeVec);

            // Step 4: Join everything into a closed solid
            var allPieces = new List<Brep>();
            allPieces.AddRange(shellPieces);
            allPieces.AddRange(walls);
            allPieces.Add(newFaceBrep);

            RhinoApp.WriteLine($"ExtrudeFaceDirect: shell={shellPieces.Count}, walls={walls.Count}, joining {allPieces.Count} pieces");
            var joined = Brep.JoinBreps(allPieces, tolerance);
            RhinoApp.WriteLine($"ExtrudeFaceDirect: join result={(joined != null ? joined.Length.ToString() + " breps" : "null")}");

            if (joined != null && joined.Length > 0)
            {
                joined[0].MergeCoplanarFaces(tolerance);
                RhinoApp.WriteLine($"ExtrudeFaceDirect: solid={joined[0].IsSolid}, faces={joined[0].Faces.Count}");

                var newId = doc.Objects.Add(joined[0], rhinoObj.Attributes);
                if (newId != Guid.Empty)
                {
                    doc.Objects.Delete(objectId, true);
                    result.CreatedIds.Add(newId);
                    result.DeletedIds.Add(objectId);
                    result.Success = true;
                }
                else
                    result.Error = "Failed to add joined result to document";
            }
            else
            {
                result.Error = "JoinBreps failed — could not reassemble solid";
                RhinoApp.WriteLine("ExtrudeFaceDirect: join FAILED, original preserved");
            }

            return result;
        }

        /// <summary>
        /// Extrude a planar curve to create a solid.
        /// </summary>
        public static ExtrudeResult ExtrudeCurve(RhinoDoc doc, Guid objectId,
                                                  Vector3d direction, double distance, bool cap = true)
        {
            var result = new ExtrudeResult { GeometryType = "curve" };
            var rhinoObj = doc.Objects.FindId(objectId);
            if (rhinoObj?.Geometry is not Curve curve)
            {
                result.Error = "Object is not a curve";
                return result;
            }

            var extrudeDir = direction;
            extrudeDir.Unitize();
            extrudeDir *= distance;

            var surface = Surface.CreateExtrusion(curve, extrudeDir);
            if (surface == null)
            {
                result.Error = "Failed to create extrusion";
                return result;
            }

            var brep = surface.ToBrep();
            if (brep == null)
            {
                result.Error = "Failed to convert to Brep";
                return result;
            }

            if (cap && curve.IsClosed)
                brep = brep.CapPlanarHoles(doc.ModelAbsoluteTolerance) ?? brep;

            var newId = doc.Objects.Add(brep, rhinoObj.Attributes);
            if (newId != Guid.Empty)
            {
                result.CreatedIds.Add(newId);
                result.Success = true;
            }
            else
                result.Error = "Failed to add extruded geometry";

            return result;
        }

        /// <summary>
        /// Boolean cut (difference) — extrude a face inward and subtract from original.
        /// Negative distance = cut inward, positive = boss outward.
        /// </summary>
        public static ExtrudeResult CutOrBoss(RhinoDoc doc, Guid objectId, int faceIndex,
                                               Vector3d direction, double distance, bool cap = true)
        {
            var isCut = distance < 0;
            var result = new ExtrudeResult
            {
                GeometryType = "face",
                BooleanOperation = isCut ? "difference" : "union"
            };

            var rhinoObj = doc.Objects.FindId(objectId);
            if (rhinoObj?.Geometry is not Brep brep)
            {
                result.Error = "Object is not a Brep";
                return result;
            }

            if (faceIndex < 0 || faceIndex >= brep.Faces.Count)
            {
                result.Error = $"Face index {faceIndex} out of range (0-{brep.Faces.Count - 1})";
                return result;
            }

            var face = brep.Faces[faceIndex];
            var faceBrep = face.DuplicateFace(false);
            if (faceBrep == null)
            {
                result.Error = "Failed to duplicate face";
                return result;
            }

            var outerLoop = faceBrep.Faces[0].OuterLoop;
            var curve = outerLoop?.To3dCurve();
            if (curve == null)
            {
                result.Error = "Failed to extract face boundary curve";
                return result;
            }

            var extrudeDir = direction;
            extrudeDir.Unitize();
            extrudeDir *= distance;

            var surface = Surface.CreateExtrusion(curve, extrudeDir);
            if (surface == null)
            {
                result.Error = "Failed to create extrusion";
                return result;
            }

            var extrudedBrep = surface.ToBrep();
            if (extrudedBrep == null)
            {
                result.Error = "Failed to convert to Brep";
                return result;
            }

            if (cap && curve.IsClosed)
                extrudedBrep = extrudedBrep.CapPlanarHoles(doc.ModelAbsoluteTolerance) ?? extrudedBrep;

            var tolerance = doc.ModelAbsoluteTolerance;
            Brep[]? boolResult;

            if (isCut)
                boolResult = Brep.CreateBooleanDifference(brep, extrudedBrep, tolerance);
            else
                boolResult = Brep.CreateBooleanUnion(new[] { brep.DuplicateBrep(), extrudedBrep }, tolerance);

            if (boolResult != null && boolResult.Length > 0)
            {
                // Merge coplanar faces for cleaner geometry
                boolResult[0].MergeCoplanarFaces(tolerance);

                var newId = doc.Objects.Add(boolResult[0], rhinoObj.Attributes);
                if (newId != Guid.Empty)
                {
                    doc.Objects.Delete(objectId, true);
                    result.CreatedIds.Add(newId);
                    result.DeletedIds.Add(objectId);
                    result.Success = true;
                }
                else
                    result.Error = "Failed to add boolean result";
            }
            else
                result.Error = $"Boolean {(isCut ? "difference" : "union")} failed — faces may not be planar or closed";

            return result;
        }

        /// <summary>
        /// Get the extrude axis direction from a GumballHandleMode.
        /// Returns null if the mode is not an extrude or cut mode.
        /// </summary>
        public static Vector3d? GetExtrudeAxis(Models.GumballHandleMode mode)
        {
            return mode switch
            {
                Models.GumballHandleMode.ExtrudeX or Models.GumballHandleMode.CutX => Vector3d.XAxis,
                Models.GumballHandleMode.ExtrudeY or Models.GumballHandleMode.CutY => Vector3d.YAxis,
                Models.GumballHandleMode.ExtrudeZ or Models.GumballHandleMode.CutZ => Vector3d.ZAxis,
                _ => null
            };
        }

        /// <summary>
        /// Check if a GumballHandleMode is an extrude mode (not cut).
        /// </summary>
        public static bool IsExtrudeMode(Models.GumballHandleMode mode)
        {
            return mode == Models.GumballHandleMode.ExtrudeX
                || mode == Models.GumballHandleMode.ExtrudeY
                || mode == Models.GumballHandleMode.ExtrudeZ;
        }

        /// <summary>
        /// Check if a GumballHandleMode is a cut mode.
        /// </summary>
        public static bool IsCutMode(Models.GumballHandleMode mode)
        {
            return mode == Models.GumballHandleMode.CutX
                || mode == Models.GumballHandleMode.CutY
                || mode == Models.GumballHandleMode.CutZ;
        }
    }
}
