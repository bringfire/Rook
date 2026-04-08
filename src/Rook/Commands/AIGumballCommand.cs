using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Runtime.InteropServices;
using Rhino;
using Rhino.Commands;
using Rhino.Display;
using Rhino.DocObjects;
using Rhino.Geometry;
using Rhino.Input.Custom;
using Rhino.UI.Gumball;
using Rook.Handlers;
using Rook.Models;

namespace Rook.Commands
{
    /// <summary>
    /// Toggle command: _AIGumball turns AI gumball mode on/off.
    /// When ON, a persistent gumball appears on selected objects.
    /// Drag handles via mouse — no blocking command loop.
    /// </summary>
    public class AIGumballCommand : Command
    {
        public override string EnglishName => "AIGumball";

        protected override Result RunCommand(RhinoDoc doc, RunMode mode)
        {
            var manager = AIGumballManager.Instance;

            if (manager.IsEnabled)
            {
                manager.Disable();
                RhinoApp.WriteLine("AI Gumball: OFF");
            }
            else
            {
                manager.Enable();
                RhinoApp.WriteLine("AI Gumball: ON — select objects to show gumball.");
            }

            return Result.Success;
        }
    }

    /// <summary>
    /// Gumball frame alignment mode — controls which coordinate system the gumball axes follow.
    /// </summary>
    public enum GumballAlignment
    {
        BoundingBox,  // Default — axes from bounding box (world-aligned)
        World,        // World X/Y/Z at object centroid
        CPlane        // Active construction plane at object centroid
    }

    /// <summary>
    /// Manages persistent AI gumball state: selection events, display conduit, and mouse handler.
    /// No blocking commands — all interaction through MouseCallback.
    /// </summary>
    public class AIGumballManager
    {
        public static AIGumballManager Instance { get; } = new AIGumballManager();

        // --- Public State ---
        public bool IsEnabled { get; private set; }
        public bool IsDragActive => _mouseHandler?.IsDragging ?? false;

        // Drag statistics (thread-safe)
        private int _currentDragCount;
        private GumballHandleMode _lastMode;
        private Transform _currentCumulativeTransform = Transform.Identity;
        private readonly object _stateLock = new object();

        // Display
#pragma warning disable CS0612 // GumballDisplayConduit() is obsolete but has no replacement
        internal GumballDisplayConduit? Conduit;
#pragma warning restore CS0612
        internal GumballObject? Gumball;
        internal GumballAppearanceSettings? Appearance;

        // Selection
        internal List<Guid> SelectedObjectIds = new List<Guid>();
        internal List<SubObjectSelection> SubObjectSelections = new List<SubObjectSelection>();

        // Mouse handler
        private AIGumballMouseHandler? _mouseHandler;

        // Alignment mode for gumball frame
        internal GumballAlignment Alignment = GumballAlignment.BoundingBox;

        // Drag behavior settings
        internal double DragStrength = 1.0;        // Multiplier for drag sensitivity (0.1 = fine, 5.0 = coarse)
        internal bool AutoReset;                    // Reset gumball to object center after each drag
        internal bool SnapEnabled;                  // Snap to grid increments
        internal double SnapTranslate = 1.0;        // Snap increment for translation
        internal double SnapRotateDeg = 15.0;       // Snap increment for rotation (degrees)
        internal double SnapScale = 0.1;            // Snap increment for scale

        // Deferred selection update (prevents gumball disappearing during sub-object selection transitions)
        private bool _selectionUpdatePending;

        private AIGumballManager() { }

        // --- Accessors for HTTP status endpoints ---
        public int CurrentDragCount { get { lock (_stateLock) return _currentDragCount; } }
        public GumballHandleMode LastMode { get { lock (_stateLock) return _lastMode; } }
        public Transform CurrentCumulativeTransform { get { lock (_stateLock) return _currentCumulativeTransform; } }

        // ==================== Enable / Disable ====================

        public void Enable()
        {
            if (IsEnabled) return;
            IsEnabled = true;

            Appearance = new GumballAppearanceSettings();
            Appearance.MenuEnabled = false;

            // Hook selection events
            RhinoDoc.SelectObjects += OnSelectObjects;
            RhinoDoc.DeselectObjects += OnDeselectObjects;
            RhinoDoc.DeselectAllObjects += OnDeselectAllObjects;

            // Enable mouse handler
            _mouseHandler = new AIGumballMouseHandler(this);
            _mouseHandler.Enabled = true;

            // Show gumball on current selection (if any)
            var doc = RhinoDoc.ActiveDoc;
            if (doc != null)
                UpdateSelectionAndGumball(doc);
        }

        public void Disable()
        {
            if (!IsEnabled) return;
            IsEnabled = false;

            // Unhook events
            RhinoDoc.SelectObjects -= OnSelectObjects;
            RhinoDoc.DeselectObjects -= OnDeselectObjects;
            RhinoDoc.DeselectAllObjects -= OnDeselectAllObjects;
            RhinoApp.Idle -= OnDeferredSelectionUpdate;
            _selectionUpdatePending = false;

            // Disable mouse handler
            if (_mouseHandler != null)
            {
                _mouseHandler.Enabled = false;
                _mouseHandler = null;
            }

            // Clean up display
            DisposeConduit();

            // Reset stats
            lock (_stateLock)
            {
                _currentDragCount = 0;
                _lastMode = GumballHandleMode.None;
                _currentCumulativeTransform = Transform.Identity;
            }
            SelectedObjectIds.Clear();
            SubObjectSelections.Clear();
        }

        // ==================== Selection Events ====================

        private void OnSelectObjects(object sender, RhinoObjectSelectionEventArgs e)
        {
            RhinoApp.WriteLine($"AIGumball [SELECT]: {e.RhinoObjects.Length} objs, IsDragActive={IsDragActive}");
            if (!IsEnabled || IsDragActive) return;
            if (_selectionUpdatePending)
            {
                RhinoApp.Idle -= OnDeferredSelectionUpdate;
                _selectionUpdatePending = false;
            }
            var doc = e.Document ?? RhinoDoc.ActiveDoc;
            // Pass event objects — GetSelectedObjects misses sub-object-only selections
            if (doc != null) UpdateSelectionAndGumball(doc, e.RhinoObjects);
        }

        private void OnDeselectObjects(object sender, RhinoObjectSelectionEventArgs e)
        {
            RhinoApp.WriteLine($"AIGumball [DESELECT]: {e.RhinoObjects.Length} objs, IsDragActive={IsDragActive}");
            if (!IsEnabled || IsDragActive) return;
            if (!_selectionUpdatePending)
            {
                _selectionUpdatePending = true;
                RhinoApp.Idle += OnDeferredSelectionUpdate;
            }
        }

        private void OnDeselectAllObjects(object sender, RhinoDeselectAllObjectsEventArgs e)
        {
            RhinoApp.WriteLine($"AIGumball [DESELECT_ALL]: IsDragActive={IsDragActive}");
            if (!IsEnabled || IsDragActive) return;
            if (!_selectionUpdatePending)
            {
                _selectionUpdatePending = true;
                RhinoApp.Idle += OnDeferredSelectionUpdate;
            }
        }

        private void OnDeferredSelectionUpdate(object sender, EventArgs e)
        {
            RhinoApp.Idle -= OnDeferredSelectionUpdate;
            _selectionUpdatePending = false;
            RhinoApp.WriteLine("AIGumball [DEFERRED]: running update");
            if (!IsEnabled || IsDragActive) return;
            var doc = RhinoDoc.ActiveDoc;
            if (doc != null) UpdateSelectionAndGumball(doc);
        }

        // ==================== Gumball Display ====================

        internal void UpdateSelectionAndGumball(RhinoDoc doc, Rhino.DocObjects.RhinoObject[]? eventObjects = null)
        {
            SelectedObjectIds.Clear();
            SubObjectSelections.Clear();

            var seen = new HashSet<Guid>();

            // Standard query — works for whole-object selections
            foreach (var obj in doc.Objects.GetSelectedObjects(false, false))
            {
                if (!seen.Add(obj.Id)) continue;
                AddObjectSelection(obj);
            }

            // Merge event objects — GetSelectedObjects misses sub-object-only selections
            if (eventObjects != null)
            {
                foreach (var obj in eventObjects)
                {
                    if (obj != null && seen.Add(obj.Id))
                        AddObjectSelection(obj);
                }
            }

            RhinoApp.WriteLine($"AIGumball [UPDATE]: total={SelectedObjectIds.Count} objs, {SubObjectSelections.Count} subs");

            if (SelectedObjectIds.Count > 0)
                ShowGumball(doc);
            else
                HideConduit();
        }

        private void AddObjectSelection(Rhino.DocObjects.RhinoObject obj)
        {
            SelectedObjectIds.Add(obj.Id);
            var selectedSubs = obj.GetSelectedSubObjects();
            if (selectedSubs != null)
            {
                foreach (var ci in selectedSubs)
                {
                    RhinoApp.WriteLine($"AIGumball [UPDATE]:   sub={ci.ComponentIndexType} idx={ci.Index}");
                    SubObjectSelections.Add(new SubObjectSelection
                    {
                        ObjectId = obj.Id.ToString(),
                        ComponentType = ci.ComponentIndexType.ToString(),
                        ComponentIndex = ci.Index
                    });
                }
            }
        }

        internal void ShowGumball(RhinoDoc doc)
        {
            var bbox = ComputeBoundingBox(doc, SelectedObjectIds, SubObjectSelections);
            RhinoApp.WriteLine($"AIGumball [SHOW]: bbox valid={bbox.IsValid} min={bbox.Min} max={bbox.Max}");
            if (!bbox.IsValid) return;

            try { Gumball?.Dispose(); } catch { }
            Gumball = new GumballObject();

            switch (Alignment)
            {
                case GumballAlignment.World:
                    Gumball.SetFromPlane(new Plane(bbox.Center, Vector3d.XAxis, Vector3d.YAxis));
                    break;
                case GumballAlignment.CPlane:
                    var view = doc.Views?.ActiveView;
                    if (view?.ActiveViewport != null)
                    {
                        var cplane = view.ActiveViewport.GetConstructionPlane().Plane;
                        cplane.Origin = bbox.Center;
                        Gumball.SetFromPlane(cplane);
                    }
                    else
                        Gumball.SetFromBoundingBox(bbox);
                    break;
                default:
                    Gumball.SetFromBoundingBox(bbox);
                    break;
            }

            if (Conduit == null)
            {
#pragma warning disable CS0612
                Conduit = new GumballDisplayConduit();
#pragma warning restore CS0612
            }

            Conduit.SetBaseGumball(Gumball, Appearance ?? new GumballAppearanceSettings());
            Conduit.Enabled = true;
            doc.Views.Redraw();
        }

        internal void HideConduit()
        {
            RhinoApp.WriteLine("AIGumball [HIDE]: hiding conduit");
            if (Conduit != null)
                Conduit.Enabled = false;
            RhinoDoc.ActiveDoc?.Views.Redraw();
        }

        private void DisposeConduit()
        {
            if (Conduit != null)
            {
                Conduit.Enabled = false;
                try { Conduit.Dispose(); } catch { }
                Conduit = null;
            }
            if (Gumball != null)
            {
                try { Gumball.Dispose(); } catch { }
                Gumball = null;
            }
            RhinoDoc.ActiveDoc?.Views.Redraw();
        }

        // ==================== Stats Tracking ====================

        internal void RecordDragStats(int count, GumballHandleMode mode, Transform cumulative)
        {
            lock (_stateLock)
            {
                _currentDragCount = count;
                _lastMode = mode;
                _currentCumulativeTransform = cumulative;
            }
        }

        // ==================== Alignment ====================

        internal bool SetAlignment(string mode)
        {
            switch (mode.ToLowerInvariant())
            {
                case "world": Alignment = GumballAlignment.World; break;
                case "cplane": Alignment = GumballAlignment.CPlane; break;
                case "bbox": case "object": case "default": Alignment = GumballAlignment.BoundingBox; break;
                default: return false;
            }

            var doc = RhinoDoc.ActiveDoc;
            if (doc != null && SelectedObjectIds.Count > 0)
                ShowGumball(doc);
            return true;
        }

        // ==================== Settings ====================

        internal Dictionary<string, object> GetSettings()
        {
            return new Dictionary<string, object>
            {
                ["alignment"] = Alignment.ToString(),
                ["dragStrength"] = DragStrength,
                ["autoReset"] = AutoReset,
                ["snapEnabled"] = SnapEnabled,
                ["snapTranslate"] = SnapTranslate,
                ["snapRotateDeg"] = SnapRotateDeg,
                ["snapScale"] = SnapScale
            };
        }

        // ==================== Helpers ====================

        internal static BoundingBox ComputeBoundingBox(RhinoDoc doc, List<Guid> objectIds, List<SubObjectSelection> subSels)
        {
            var bbox = BoundingBox.Empty;

            if (subSels.Count > 0)
            {
                foreach (var sub in subSels)
                {
                    if (!Guid.TryParse(sub.ObjectId, out var objId)) continue;
                    var rhinoObj = doc.Objects.FindId(objId);
                    if (rhinoObj == null) continue;
                    var subBbox = GetSubObjectBoundingBox(rhinoObj.Geometry, sub);
                    if (subBbox.IsValid)
                        bbox.Union(subBbox);
                }

                // For sub-objects, inflate degenerate bboxes (edges=lines, vertices=points)
                // instead of falling back to whole-object bbox
                if (bbox.IsValid)
                {
                    if (bbox.IsDegenerate(doc.ModelAbsoluteTolerance) > 0)
                    {
                        var diag = bbox.Diagonal.Length;
                        var pad = Math.Max(diag * 0.15, doc.ModelAbsoluteTolerance * 100);
                        bbox.Inflate(pad, pad, pad);
                    }
                    return bbox;
                }
            }

            // Whole-object fallback (no sub-objects selected, or sub-object bbox failed)
            bbox = BoundingBox.Empty;
            foreach (var objId in objectIds)
            {
                var rhinoObj = doc.Objects.FindId(objId);
                if (rhinoObj == null) continue;
                var objBbox = rhinoObj.Geometry.GetBoundingBox(true);
                if (objBbox.IsValid)
                    bbox.Union(objBbox);
            }

            return bbox;
        }

        internal static BoundingBox GetSubObjectBoundingBox(GeometryBase geometry, SubObjectSelection sub)
        {
            if (geometry is Brep brep)
            {
                if (sub.ComponentType == "BrepFace" && sub.ComponentIndex >= 0 && sub.ComponentIndex < brep.Faces.Count)
                    return brep.Faces[sub.ComponentIndex].GetBoundingBox(true);
                if (sub.ComponentType == "BrepEdge" && sub.ComponentIndex >= 0 && sub.ComponentIndex < brep.Edges.Count)
                    return brep.Edges[sub.ComponentIndex].GetBoundingBox(true);
                if (sub.ComponentType == "BrepVertex" && sub.ComponentIndex >= 0 && sub.ComponentIndex < brep.Vertices.Count)
                {
                    var pt = brep.Vertices[sub.ComponentIndex].Location;
                    return new BoundingBox(pt, pt);
                }
            }
            else if (geometry is SubD subd)
            {
                return subd.GetBoundingBox(true);
            }

            return BoundingBox.Empty;
        }

        internal static double[] TransformToArray(Transform xform)
        {
            return new double[]
            {
                xform.M00, xform.M01, xform.M02, xform.M03,
                xform.M10, xform.M11, xform.M12, xform.M13,
                xform.M20, xform.M21, xform.M22, xform.M23,
                xform.M30, xform.M31, xform.M32, xform.M33
            };
        }
    }

    /// <summary>
    /// Mouse callback that uses GumballDisplayConduit.PickGumball + UpdateGumball
    /// for native handle picking and transform computation.
    /// Replaces 200+ lines of manual hit-testing and axis-projection math.
    /// Other Rhino commands work normally when not dragging a handle.
    /// </summary>
    internal class AIGumballMouseHandler : Rhino.UI.MouseCallback
    {
        private readonly AIGumballManager _manager;

        // Drag state
        public bool IsDragging { get; private set; }
        private Transform _appliedTransform = Transform.Identity;
        private GumballMode _pickedMode = GumballMode.None;

        // Sub-object drag state
        private bool _isSubObjectDrag;
        private Dictionary<Guid, GeometryBase>? _originalGeometries;

        // Session-level cumulative transform (across all drags since session start)
        private Transform _sessionCumulativeTransform = Transform.Identity;
        private bool _shiftHeldDuringDrag; // Shift = uniform scale (native Rhino behavior)
        private bool _ctrlHeldDuringDrag; // Ctrl+drag on sub-object = extrude (new walls)
        private bool _altHeldDuringDrag;  // Alt+drag = copy object

        // Drag history for session recording
        private readonly List<GumballDragRecord> _dragHistory = new List<GumballDragRecord>();
        private readonly List<string> _objectsCreated = new List<string>();
        private Stopwatch? _dragStopwatch;
        private Stopwatch? _sessionStopwatch;
        private int _totalDragCount;

        // Undo scope for current drag (captures all doc modifications as one undoable unit)
        private UndoScope? _currentUndoScope;

        // Extrude/Cut drag state
        private bool _isExtrudeDrag;
        private bool _isCutDrag;
        private Vector3d _extrudeAxis;

        public AIGumballMouseHandler(AIGumballManager manager)
        {
            _manager = manager;
        }

        // ==================== Mouse Events ====================

        protected override void OnMouseDown(Rhino.UI.MouseCallbackEventArgs e)
        {
            // Right-click during drag cancels and reverts
            if (IsDragging && !IsLeftButton(e))
            {
                CancelDrag();
                e.Cancel = true;
                return;
            }

            if (!_manager.IsEnabled || IsDragging) return;
            if (_manager.SelectedObjectIds.Count == 0) return;

            var conduit = _manager.Conduit;
            if (conduit == null || !conduit.Enabled) return;
            if (!IsLeftButton(e)) return;

            var view = e.View;
            if (view == null) return;
            var vp = view.ActiveViewport;

            // Build proper PickContext — these 3 setup calls were missing in v1
            var pick = new PickContext();
            pick.View = view;
            pick.PickStyle = PickStyle.PointPick;
            pick.SetPickTransform(vp.GetPickTransform(e.ViewportPoint));

            if (vp.GetFrustumLine(e.ViewportPoint.X, e.ViewportPoint.Y, out Line pickLine))
                pick.PickLine = pickLine;

            pick.UpdateClippingPlanes();

            // Native handle hit-test — conduit knows its own geometry
            if (!conduit.PickGumball(pick, null))
                return; // Didn't hit any handle — let Rhino process normally

            _pickedMode = conduit.PickResult.Mode;
            if (_pickedMode == GumballMode.None)
                return;

            IsDragging = true;
            _appliedTransform = Transform.Identity;
            _shiftHeldDuringDrag = false;
            _ctrlHeldDuringDrag = IsCtrlDown();
            _altHeldDuringDrag = IsAltDown();
            _dragStopwatch = Stopwatch.StartNew();

            // Open undo scope to capture this drag as one undoable unit
            var undoDoc = RhinoDoc.ActiveDoc;
            if (undoDoc != null)
                _currentUndoScope = new UndoScope(undoDoc, $"AIGumball {_pickedMode}");

            if (_sessionStopwatch == null)
            {
                _sessionStopwatch = Stopwatch.StartNew();
                _sessionCumulativeTransform = Transform.Identity;
                _dragHistory.Clear();
                _objectsCreated.Clear();
                _totalDragCount = 0;
            }

            // Detect extrude/cut mode from SDK handle type only
            // (Sub-object face extrude uses TransformComponent, not these flags)
            var mappedMode = MapGumballMode(_pickedMode);
            _isExtrudeDrag = GumballExtrudeHandler.IsExtrudeMode(mappedMode);
            _isCutDrag = GumballExtrudeHandler.IsCutMode(mappedMode);
            _extrudeAxis = GumballExtrudeHandler.GetExtrudeAxis(mappedMode) ?? Vector3d.ZAxis;

            // Save original geometry for sub-object drags (TransformComponent needs originals)
            _isSubObjectDrag = _manager.SubObjectSelections.Count > 0;
            if (_isSubObjectDrag)
            {
                _originalGeometries = new Dictionary<Guid, GeometryBase>();
                var doc = RhinoDoc.ActiveDoc;
                if (doc != null)
                {
                    foreach (var objId in _manager.SelectedObjectIds)
                    {
                        var obj = doc.Objects.FindId(objId);
                        if (obj?.Geometry != null)
                            _originalGeometries[objId] = obj.Geometry.Duplicate();
                    }
                }
            }

            RhinoApp.WriteLine($"AIGumball: dragging {_pickedMode} (subObject={_isSubObjectDrag}, ctrl={_ctrlHeldDuringDrag}, alt={_altHeldDuringDrag})");
            e.Cancel = true;
        }

        protected override void OnMouseMove(Rhino.UI.MouseCallbackEventArgs e)
        {
            if (!IsDragging) return;

            var conduit = _manager.Conduit;
            if (conduit == null) return;

            var view = e.View;
            if (view == null) return;
            var vp = view.ActiveViewport;

            // Get frustum line for this mouse position
            if (!vp.GetFrustumLine(e.ViewportPoint.X, e.ViewportPoint.Y, out Line worldLine))
                return;

            // Compute 3D drag point by intersecting frustum line with construction plane
            var cplane = vp.GetConstructionPlane().Plane;
            if (!Rhino.Geometry.Intersect.Intersection.LinePlane(worldLine, cplane, out double lp))
                return;
            var dragPoint = worldLine.PointAt(lp);

            // Apply drag strength scaling (scales displacement from gumball center)
            if (Math.Abs(_manager.DragStrength - 1.0) > 0.001 && _manager.Gumball != null)
            {
                var gumballFrame = _manager.Gumball.Frame;
                var center = gumballFrame.Plane.Origin;
                var offset = dragPoint - center;
                dragPoint = center + offset * _manager.DragStrength;
            }

            // Track modifier keys (latch — once detected, stays true for the drag)
            if (!_shiftHeldDuringDrag)
                _shiftHeldDuringDrag = IsShiftDown(e);
            if (!_ctrlHeldDuringDrag)
                _ctrlHeldDuringDrag = IsCtrlDown();
            if (!_altHeldDuringDrag)
                _altHeldDuringDrag = IsAltDown();

            // Let conduit detect shift/ctrl state — but skip when sub-object is selected,
            // because Ctrl+drag on a sub-object face = extrude (TransformComponent),
            // and CheckShiftAndControlKeys would set InRelocate=true blocking the transform.
            if (!_isSubObjectDrag)
                conduit.CheckShiftAndControlKeys();

            // Native transform computation — conduit handles all the math
            if (!conduit.UpdateGumball(dragPoint, worldLine))
                return;

            // Apply transform to objects (skip during relocate, but always allow sub-object drags)
            if (!conduit.InRelocate || _isSubObjectDrag)
            {
                var totalXform = conduit.TotalTransform;

                // Shift + scale handle = uniform scale (matches native Rhino gumball behavior).
                // The conduit computes single-axis scale — we extract the factor and apply it uniformly.
                if (_shiftHeldDuringDrag && IsScaleHandle(_pickedMode) && _manager.Gumball != null)
                {
                    var gp = _manager.Gumball.Frame.Plane;
                    var scaleAxis = _pickedMode switch
                    {
                        GumballMode.ScaleX or GumballMode.ScaleXY => gp.XAxis,
                        GumballMode.ScaleY or GumballMode.ScaleYZ => gp.YAxis,
                        _ => gp.ZAxis // ScaleZ, ScaleZX
                    };

                    // Measure how the conduit's transform scaled this axis
                    var p0 = gp.Origin;
                    var p1 = gp.Origin + scaleAxis;
                    p0.Transform(totalXform);
                    p1.Transform(totalXform);
                    var diff = p1 - p0;
                    var scaleFactor = diff.Length;
                    if (diff * scaleAxis < 0) scaleFactor = -scaleFactor;

                    // Replace with uniform scale from gumball center
                    totalXform = Transform.Scale(gp.Origin, scaleFactor);
                }

                // Snap translation to grid increments (only for translation handles —
                // rotation/scale encode pivot offset in M03/M13/M23, rounding corrupts them)
                if (_manager.SnapEnabled && totalXform.IsValid && IsTranslationHandle(_pickedMode))
                {
                    var snap = _manager.SnapTranslate;
                    totalXform.M03 = Math.Round(totalXform.M03 / snap) * snap;
                    totalXform.M13 = Math.Round(totalXform.M13 / snap) * snap;
                    totalXform.M23 = Math.Round(totalXform.M23 / snap) * snap;
                }

                if (totalXform.IsValid)
                {
                    if (_isExtrudeDrag || _isCutDrag)
                    {
                        // Extrude/Cut: defer geometry to mouse-up. Gumball conduit provides visual feedback.
                        _appliedTransform = totalXform;
                    }
                    else if (_isSubObjectDrag)
                    {
                        // Sub-object: defer geometry to mouse-up. Gumball conduit provides visual feedback.
                        _appliedTransform = totalXform;
                    }
                    else
                    {
                        // Whole object: apply incremental delta in real-time (in-place, cheap)
                        var doc = RhinoDoc.ActiveDoc;
                        if (doc != null && _appliedTransform.TryGetInverse(out Transform invApplied))
                        {
                            var delta = totalXform * invApplied;
                            if (delta != Transform.Identity)
                            {
                                foreach (var objId in _manager.SelectedObjectIds)
                                    doc.Objects.Transform(objId, delta, true);
                            }
                            _appliedTransform = totalXform;
                        }
                    }
                }
            }

            RhinoDoc.ActiveDoc?.Views.Redraw();
            e.Cancel = true;
        }

        protected override void OnMouseUp(Rhino.UI.MouseCallbackEventArgs e)
        {
            if (!IsDragging) return;
            if (!IsLeftButton(e)) return;

            FinalizeDrag();
            e.Cancel = true;
        }

        // ==================== Drag Finalization ====================

        private void FinalizeDrag()
        {
            _dragStopwatch?.Stop();
            IsDragging = false;

            try
            {
                var conduit = _manager.Conduit;
                bool isRelocate = conduit?.InRelocate ?? false;

                // Record this drag
                _totalDragCount++;
                var handleMode = MapGumballMode(_pickedMode);

                // Update session cumulative (skip relocates — they don't transform geometry)
                if (!isRelocate)
                    _sessionCumulativeTransform = _sessionCumulativeTransform * _appliedTransform;

                _dragHistory.Add(new GumballDragRecord
                {
                    DragIndex = _totalDragCount,
                    HandleMode = handleMode,
                    DeltaTransformMatrix = AIGumballManager.TransformToArray(_appliedTransform),
                    CumulativeTransformMatrix = AIGumballManager.TransformToArray(_sessionCumulativeTransform),
                    IsCopy = _altHeldDuringDrag,
                    IsRelocate = isRelocate,
                    Timestamp = DateTime.UtcNow,
                    DragDurationMs = _dragStopwatch?.Elapsed.TotalMilliseconds ?? 0,
                    DragStrength = _manager.DragStrength
                });

                _manager.RecordDragStats(_totalDragCount, handleMode, _sessionCumulativeTransform);
                RhinoApp.WriteLine($"AIGumball: drag {_totalDragCount} complete ({handleMode}, subObject={_isSubObjectDrag}).");

                // Extrude/Cut: compute distance from transform and apply geometry operation
                // Only for whole-object drags — sub-object face drags use TransformComponent
                // (which extends adjacent faces automatically, like native Rhino gumball)
                if ((_isExtrudeDrag || _isCutDrag) && !isRelocate && !_isSubObjectDrag)
                {
                    var extDoc = RhinoDoc.ActiveDoc;
                    if (extDoc != null)
                    {
                        // Project translation onto the gumball frame's axis (not world axis)
                        // to handle CPlane/rotated gumball alignments correctly
                        var translation = new Vector3d(_appliedTransform.M03, _appliedTransform.M13, _appliedTransform.M23);
                        var extrudeWorldAxis = _extrudeAxis;
                        var gumballPlane = _manager.Gumball?.Frame.Plane;
                        if (gumballPlane.HasValue)
                        {
                            var gp = gumballPlane.Value;
                            extrudeWorldAxis = handleMode switch
                            {
                                GumballHandleMode.ExtrudeX or GumballHandleMode.CutX or GumballHandleMode.TranslateX => gp.XAxis,
                                GumballHandleMode.ExtrudeY or GumballHandleMode.CutY or GumballHandleMode.TranslateY => gp.YAxis,
                                _ => gp.ZAxis // ExtrudeZ, CutZ, TranslateZ
                            };
                        }
                        var extrudeDistance = translation * extrudeWorldAxis;

                        if (Math.Abs(extrudeDistance) > extDoc.ModelAbsoluteTolerance)
                        {
                            var lastDrag = _dragHistory.Last();
                            lastDrag.ExtrudeDistance = extrudeDistance;
                            lastDrag.ExtrudeCapped = true;
                            lastDrag.ObjectsCreated ??= new List<string>();
                            lastDrag.ObjectsDeleted ??= new List<string>();

                            foreach (var objId in _manager.SelectedObjectIds.ToList())
                            {
                                Handlers.ExtrudeResult extResult;

                                if (_isSubObjectDrag && _manager.SubObjectSelections.Count > 0)
                                {
                                    var faceSel = _manager.SubObjectSelections.FirstOrDefault(s => s.ComponentType == "BrepFace");
                                    if (faceSel != null)
                                    {
                                        extResult = _isCutDrag
                                            ? GumballExtrudeHandler.CutOrBoss(extDoc, objId, faceSel.ComponentIndex, extrudeWorldAxis, extrudeDistance)
                                            : GumballExtrudeHandler.ExtrudeFace(extDoc, objId, faceSel.ComponentIndex, extrudeWorldAxis, extrudeDistance);
                                    }
                                    else
                                        continue;
                                }
                                else
                                {
                                    var rhinoObj = extDoc.Objects.FindId(objId);
                                    if (rhinoObj?.Geometry is Curve)
                                        extResult = GumballExtrudeHandler.ExtrudeCurve(extDoc, objId, extrudeWorldAxis, extrudeDistance);
                                    else if (rhinoObj?.Geometry is Brep brepObj)
                                    {
                                        // Find the face whose normal best aligns with the drag direction
                                        int bestFace = 0;
                                        if (brepObj.Faces.Count > 1)
                                        {
                                            var searchDir = extrudeDistance >= 0 ? extrudeWorldAxis : -extrudeWorldAxis;
                                            double bestDot = double.MinValue;
                                            for (int i = 0; i < brepObj.Faces.Count; i++)
                                            {
                                                var normal = brepObj.Faces[i].NormalAt(
                                                    brepObj.Faces[i].Domain(0).Mid,
                                                    brepObj.Faces[i].Domain(1).Mid);
                                                var dot = normal * searchDir;
                                                if (dot > bestDot)
                                                {
                                                    bestDot = dot;
                                                    bestFace = i;
                                                }
                                            }
                                        }

                                        extResult = _isCutDrag
                                            ? GumballExtrudeHandler.CutOrBoss(extDoc, objId, bestFace, extrudeWorldAxis, extrudeDistance)
                                            : GumballExtrudeHandler.ExtrudeFace(extDoc, objId, bestFace, extrudeWorldAxis, extrudeDistance);
                                    }
                                    else
                                    {
                                        extResult = new Handlers.ExtrudeResult { Error = "Object type not supported for extrude" };
                                    }
                                }

                                if (extResult.Success)
                                {
                                    lastDrag.ExtrudeGeometryType = extResult.GeometryType;
                                    lastDrag.BooleanOperation = extResult.BooleanOperation;
                                    lastDrag.ObjectsCreated.AddRange(extResult.CreatedIds.Select(g => g.ToString()));
                                    lastDrag.ObjectsDeleted.AddRange(extResult.DeletedIds.Select(g => g.ToString()));
                                    _objectsCreated.AddRange(extResult.CreatedIds.Select(g => g.ToString()));
                                }
                                else
                                {
                                    RhinoApp.WriteLine($"AIGumball: extrude failed: {extResult.Error}");
                                }
                            }

                            // Update selection to point to newly created objects
                            // (originals were deleted by boolean operations)
                            // Select in Rhino so click-away deselect works properly
                            var createdIds = lastDrag.ObjectsCreated;
                            if (createdIds != null && createdIds.Count > 0)
                            {
                                _manager.SelectedObjectIds.Clear();
                                _manager.SubObjectSelections.Clear();
                                foreach (var idStr in createdIds)
                                {
                                    if (Guid.TryParse(idStr, out var newGuid))
                                    {
                                        _manager.SelectedObjectIds.Add(newGuid);
                                        var newObj = extDoc.Objects.FindId(newGuid);
                                        newObj?.Select(true);
                                    }
                                }
                            }
                        }
                    }
                }
                // Copy-on-drag: Alt was held during a geometry-modifying whole-object drag
                else if (_altHeldDuringDrag && !isRelocate && !_isSubObjectDrag)
                {
                    var copyDoc = RhinoDoc.ActiveDoc;
                    if (copyDoc != null && _appliedTransform.TryGetInverse(out Transform invXform))
                    {
                        foreach (var objId in _manager.SelectedObjectIds)
                            copyDoc.Objects.Transform(objId, invXform, true);

                        foreach (var objId in _manager.SelectedObjectIds)
                        {
                            var rhinoObj = copyDoc.Objects.FindId(objId);
                            if (rhinoObj == null) continue;

                            var dupGeom = rhinoObj.Geometry.Duplicate();
                            dupGeom.Transform(_appliedTransform);
                            var dupAttrs = rhinoObj.Attributes.Duplicate();
                            var dupId = copyDoc.Objects.Add(dupGeom, dupAttrs);
                            if (dupId != Guid.Empty)
                                _objectsCreated.Add(dupId.ToString());
                        }
                    }
                    else if (copyDoc != null)
                    {
                        RhinoApp.WriteLine("AIGumball: Alt+copy failed — transform is not invertible.");
                    }
                }

                // Apply sub-object operation (deferred from mouse-move for smooth dragging)
                if (_isSubObjectDrag && _originalGeometries != null && !isRelocate)
                {
                    var applyDoc = RhinoDoc.ActiveDoc;
                    if (applyDoc != null)
                    {
                        if (_ctrlHeldDuringDrag)
                        {
                            // Ctrl+drag = TRUE EXTRUDE: face moves, new wall faces created
                            // between original and new position (like native Rhino gumball)
                            ApplySubObjectExtrude(applyDoc);
                        }
                        else
                        {
                            // Normal drag = move/deform: TransformComponent stretches adjacent faces
                            ApplySubObjectTransform(applyDoc, _appliedTransform);
                        }
                    }
                }

                // Clean up sub-object state
                _originalGeometries = null;

                // Rebuild gumball from transformed geometry (resets conduit transform state)
                var doc = RhinoDoc.ActiveDoc;
                if (doc != null)
                    _manager.ShowGumball(doc);
            }
            finally
            {
                // Always close undo scope even if an exception occurred
                DisposeUndoScope();
            }

            // Record to session (outside try/finally — non-critical)
            RecordToSession();

            // Auto-reset: clear session tracking so each drag is independent
            if (_manager.AutoReset)
            {
                _sessionStopwatch = null;
                _sessionCumulativeTransform = Transform.Identity;
            }
        }

        private void CancelDrag()
        {
            _dragStopwatch?.Stop();
            IsDragging = false;

            if (_isSubObjectDrag || _isExtrudeDrag || _isCutDrag)
            {
                // Sub-object/extrude/cut: geometry was never modified during drag (deferred), just clean up
                _originalGeometries = null;
            }
            else
            {
                // Revert applied transform (whole object)
                if (_appliedTransform != Transform.Identity &&
                    _appliedTransform.TryGetInverse(out Transform inverse) &&
                    inverse.IsValid)
                {
                    var doc = RhinoDoc.ActiveDoc;
                    if (doc != null)
                    {
                        foreach (var objId in _manager.SelectedObjectIds)
                            doc.Objects.Transform(objId, inverse, true);
                    }
                }
            }

            // Rebuild gumball at original position
            var activeDoc = RhinoDoc.ActiveDoc;
            if (activeDoc != null)
                _manager.ShowGumball(activeDoc);

            RhinoApp.WriteLine("AIGumball: drag cancelled.");

            // Close undo scope (forward + revert = identity, harmless undo entry)
            DisposeUndoScope();
        }

        private void DisposeUndoScope()
        {
            if (_currentUndoScope.HasValue)
            {
                var scope = _currentUndoScope.Value;
                _currentUndoScope = null;
                scope.Dispose();
            }
        }

        private void RecordToSession()
        {
            try
            {
                if (_dragHistory.Count == 0) return;

                var record = new CommandRecord
                {
                    Timestamp = DateTime.UtcNow,
                    Source = CommandSource.User,
                    CommandName = "AIGumball",
                    Success = true,
                    DurationMs = _sessionStopwatch?.Elapsed.TotalMilliseconds ?? 0,
                    InputObjectIds = _manager.SelectedObjectIds.Select(g => g.ToString()).ToList(),
                    InputSubObjects = _manager.SubObjectSelections.Count > 0 ? new List<SubObjectSelection>(_manager.SubObjectSelections) : null,
                    TransformedSubObjects = _manager.SubObjectSelections.Count > 0 ? new List<SubObjectSelection>(_manager.SubObjectSelections) : null,
                    GumballDrags = new List<GumballDragRecord>(_dragHistory),
                    GumballDragCount = _dragHistory.Count,
                    GumballMode = _dragHistory.Last().HandleMode.ToString(),
                    CanReplay = false
                };

                var lastNonRelocate = _dragHistory.LastOrDefault(d => !d.IsRelocate);
                if (lastNonRelocate?.CumulativeTransformMatrix != null)
                    record.TransformMatrix = lastNonRelocate.CumulativeTransformMatrix;

                if (_objectsCreated.Count > 0)
                    record.ObjectIdsCreated = new List<string>(_objectsCreated);

                SessionRecorder.Instance.RecordAIGumballCommand(record);
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"AIGumball: Session recording failed: {ex.Message}");
            }
        }

        // ==================== Sub-Object Transform ====================

        private void ApplySubObjectTransform(RhinoDoc doc, Transform totalXform)
        {
            if (_originalGeometries == null) return;

            foreach (var kvp in _originalGeometries)
            {
                if (!(kvp.Value is Brep originalBrep)) continue;

                var subIndices = _manager.SubObjectSelections
                    .Where(s => Guid.TryParse(s.ObjectId, out var id) && id == kvp.Key)
                    .Select(s => new ComponentIndex(ParseComponentType(s.ComponentType), s.ComponentIndex))
                    .ToArray();

                if (subIndices.Length == 0) continue;

                var modified = originalBrep.DuplicateBrep();
                if (modified.TransformComponent(subIndices, totalXform, doc.ModelAbsoluteTolerance, 0, false))
                    doc.Objects.Replace(kvp.Key, modified);
            }
        }

        /// <summary>
        /// Ctrl+drag sub-object extrude: face moves to new position, new wall faces
        /// are created between the original and new face positions (true extrude).
        /// Falls back to TransformComponent if the face extrude fails or no face is selected.
        /// </summary>
        private void ApplySubObjectExtrude(RhinoDoc doc)
        {
            var faceSel = _manager.SubObjectSelections.FirstOrDefault(s => s.ComponentType == "BrepFace");
            if (faceSel == null)
            {
                // No face selected (edge/vertex) — fall back to TransformComponent
                RhinoApp.WriteLine("AIGumball: Ctrl+drag on non-face sub-object, using TransformComponent");
                ApplySubObjectTransform(doc, _appliedTransform);
                return;
            }

            if (!Guid.TryParse(faceSel.ObjectId, out var objId))
                return;

            // Compute extrude direction and distance from the drag transform.
            // The gumball frame's axis tells us which world direction the handle maps to.
            var translation = new Vector3d(_appliedTransform.M03, _appliedTransform.M13, _appliedTransform.M23);
            var extrudeWorldAxis = Vector3d.ZAxis;
            var gumballPlane = _manager.Gumball?.Frame.Plane;
            if (gumballPlane.HasValue)
            {
                var gp = gumballPlane.Value;
                extrudeWorldAxis = _pickedMode switch
                {
                    GumballMode.TranslateX => gp.XAxis,
                    GumballMode.TranslateY => gp.YAxis,
                    _ => gp.ZAxis
                };
            }
            var extrudeDistance = translation * extrudeWorldAxis; // dot product = signed distance

            if (Math.Abs(extrudeDistance) <= doc.ModelAbsoluteTolerance)
                return;

            var extResult = GumballExtrudeHandler.ExtrudeFaceDirect(doc, objId, faceSel.ComponentIndex, extrudeWorldAxis, extrudeDistance);
            if (extResult.Success)
            {
                RhinoApp.WriteLine($"AIGumball: Ctrl+extrude face {faceSel.ComponentIndex}, distance={extrudeDistance:F3}");

                // Record extrude info for session
                var lastDrag = _dragHistory.LastOrDefault();
                if (lastDrag != null)
                {
                    lastDrag.ExtrudeDistance = extrudeDistance;
                    lastDrag.ExtrudeCapped = true;
                    lastDrag.ExtrudeGeometryType = extResult.GeometryType;
                    lastDrag.BooleanOperation = extResult.BooleanOperation;
                    lastDrag.ObjectsCreated ??= new List<string>();
                    lastDrag.ObjectsDeleted ??= new List<string>();
                    lastDrag.ObjectsCreated.AddRange(extResult.CreatedIds.Select(g => g.ToString()));
                    lastDrag.ObjectsDeleted.AddRange(extResult.DeletedIds.Select(g => g.ToString()));
                }
                _objectsCreated.AddRange(extResult.CreatedIds.Select(g => g.ToString()));

                // Update selection — original was deleted, select the new object in Rhino
                // so that clicking elsewhere properly fires deselect and hides the gumball
                if (extResult.CreatedIds.Count > 0)
                {
                    _manager.SelectedObjectIds.Clear();
                    _manager.SubObjectSelections.Clear();
                    foreach (var newId in extResult.CreatedIds)
                    {
                        _manager.SelectedObjectIds.Add(newId);
                        var newObj = doc.Objects.FindId(newId);
                        newObj?.Select(true);
                    }
                }
            }
            else
            {
                RhinoApp.WriteLine($"AIGumball: Ctrl+extrude failed ({extResult.Error}), falling back to TransformComponent");
                ApplySubObjectTransform(doc, _appliedTransform);
            }
        }

        private static ComponentIndexType ParseComponentType(string type)
        {
            return type switch
            {
                "BrepFace" => ComponentIndexType.BrepFace,
                "BrepEdge" => ComponentIndexType.BrepEdge,
                "BrepVertex" => ComponentIndexType.BrepVertex,
                "SubdFace" => ComponentIndexType.SubdFace,
                "SubdEdge" => ComponentIndexType.SubdEdge,
                "SubdVertex" => ComponentIndexType.SubdVertex,
                "MeshFace" => ComponentIndexType.MeshFace,
                "MeshVertex" => ComponentIndexType.MeshVertex,
                _ => ComponentIndexType.InvalidType
            };
        }

        // ==================== Mode Mapping ====================

        private static GumballHandleMode MapGumballMode(GumballMode mode)
        {
            return mode switch
            {
                GumballMode.TranslateX => GumballHandleMode.TranslateX,
                GumballMode.TranslateY => GumballHandleMode.TranslateY,
                GumballMode.TranslateZ => GumballHandleMode.TranslateZ,
                GumballMode.TranslateXY => GumballHandleMode.TranslateXY,
                GumballMode.TranslateYZ => GumballHandleMode.TranslateYZ,
                GumballMode.TranslateZX => GumballHandleMode.TranslateZX,
                GumballMode.TranslateFree => GumballHandleMode.TranslateFree,
                GumballMode.RotateX => GumballHandleMode.RotateX,
                GumballMode.RotateY => GumballHandleMode.RotateY,
                GumballMode.RotateZ => GumballHandleMode.RotateZ,
                GumballMode.ScaleX => GumballHandleMode.ScaleX,
                GumballMode.ScaleY => GumballHandleMode.ScaleY,
                GumballMode.ScaleZ => GumballHandleMode.ScaleZ,
                GumballMode.ScaleXY => GumballHandleMode.ScaleXY,
                GumballMode.ScaleYZ => GumballHandleMode.ScaleYZ,
                GumballMode.ScaleZX => GumballHandleMode.ScaleZX,
                GumballMode.ExtrudeX => GumballHandleMode.ExtrudeX,
                GumballMode.ExtrudeY => GumballHandleMode.ExtrudeY,
                GumballMode.ExtrudeZ => GumballHandleMode.ExtrudeZ,
                // CutX/Y/Z not in RhinoCommon 8.0.23304 enum — use int casts for forward compatibility
                (GumballMode)21 => GumballHandleMode.CutX,
                (GumballMode)22 => GumballHandleMode.CutY,
                (GumballMode)23 => GumballHandleMode.CutZ,
                GumballMode.Menu => GumballHandleMode.Menu,
                _ => GumballHandleMode.None
            };
        }

        private static bool IsTranslationHandle(GumballMode mode)
        {
            return mode == GumballMode.TranslateX || mode == GumballMode.TranslateY
                || mode == GumballMode.TranslateZ || mode == GumballMode.TranslateXY
                || mode == GumballMode.TranslateYZ || mode == GumballMode.TranslateZX
                || mode == GumballMode.TranslateFree;
        }

        private static bool IsScaleHandle(GumballMode mode)
        {
            return mode == GumballMode.ScaleX || mode == GumballMode.ScaleY
                || mode == GumballMode.ScaleZ || mode == GumballMode.ScaleXY
                || mode == GumballMode.ScaleYZ || mode == GumballMode.ScaleZX;
        }

        // ==================== Platform Helpers ====================

        /// <summary>
        /// Check if the event is a left mouse button event.
        /// Uses reflection for cross-version compatibility (net48 vs net7).
        /// </summary>
        private static bool IsLeftButton(Rhino.UI.MouseCallbackEventArgs e)
        {
            try
            {
                var prop = e.GetType().GetProperty("MouseButton");
                if (prop != null)
                {
                    var val = prop.GetValue(e);
                    return val?.ToString() == "Left";
                }

                prop = e.GetType().GetProperty("Button");
                if (prop != null)
                {
                    var val = prop.GetValue(e);
                    var str = val?.ToString() ?? "";
                    return str.Contains("Left");
                }
            }
            catch { }

            return true; // Default to left button
        }

        /// <summary>
        /// Check if the Shift key is held (for uniform scale).
        /// Uses reflection for cross-version compatibility.
        /// </summary>
        private static bool IsShiftDown(Rhino.UI.MouseCallbackEventArgs e)
        {
            try
            {
                var prop = e.GetType().GetProperty("ShiftKeyDown");
                if (prop != null)
                    return (bool)(prop.GetValue(e) ?? false);
            }
            catch { }
            return false;
        }

        /// <summary>
        /// Check if the Ctrl key is currently held.
        /// Uses Win32 GetAsyncKeyState because Rhino's MouseCallbackEventArgs
        /// does not expose Ctrl state via any accessible property.
        /// </summary>
        [DllImport("user32.dll")]
        private static extern short GetAsyncKeyState(int vKey);
        private const int VK_CONTROL = 0x11;
        private const int VK_MENU = 0x12; // Alt key

        private static bool IsCtrlDown()
        {
            return (GetAsyncKeyState(VK_CONTROL) & 0x8000) != 0;
        }

        private static bool IsAltDown()
        {
            return (GetAsyncKeyState(VK_MENU) & 0x8000) != 0;
        }

    }
}
