# PROMOTED 2026-04-22 to POST /block/distribute-along-curve
#   MCP tool:          rhino_block_distribute_along_curve
# CapabilityRouter:    block_distribute_along_curve
# Doctrine:            rook_docs/2026-04-22-exotic-capability-promotion-plan.md
# PR scope:            rook_docs/2026-04-22-exotic-capability-pr1-scope.md
#
# This file is a frozen REFERENCE ARTIFACT. Do not invoke at runtime and do
# not modify in place. The authoritative implementation lives in the native
# C++ handler HandleBlockDistributeAlongCurve in
# src/RookNative/Handlers/BlocksHandler.cpp and is exposed as a typed route.
#
# Historical note: this was the first user-authored Rhino script promoted
# into a first-class typed Rook capability under the exotic-capability
# promotion doctrine. It is preserved here because its algorithm — curve
# arc-length parameterization, upright-frame construction with a
# vertical-tangent guard, and transform composition (align → rotate → scale)
# — is still useful as a reference for future promotions of similar
# capabilities. The interactive rs.Get* shell is the part that made it
# unrunnable through the agent path (rhino_execute preflight refuses
# blocking rhinoscriptsyntax prompts) and is discarded by promotion.

import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc
import random
import math
import System
from System.Collections.Generic import List

def GetBlockDefinitions():
    """Get all block definitions in the document"""
    block_names = []
    for idef in sc.doc.InstanceDefinitions:
        if idef and not idef.IsDeleted:
            block_names.append(idef.Name)
    return block_names

def SelectBlocks():
    """Allow user to select multiple block instances"""
    # Get block instances - using the rhinoscriptsyntax filter constant
    block_ids = rs.GetObjects("Select block instances to distribute", rs.filter.instance)

    if not block_ids:
        return None

    # Get the instance definitions from selected blocks
    selected_idefs = []
    for block_id in block_ids:
        obj = sc.doc.Objects.Find(block_id)
        if obj and isinstance(obj, Rhino.DocObjects.InstanceObject):
            idef = obj.InstanceDefinition
            if idef not in selected_idefs:
                selected_idefs.append(idef)

    return selected_idefs

def SelectCurve():
    """Select a curve to distribute blocks along"""
    curve_id = rs.GetObject("Select curve to distribute blocks along", rs.filter.curve)
    if not curve_id:
        return None

    curve_obj = sc.doc.Objects.Find(curve_id)
    if curve_obj:
        return curve_obj.Geometry
    return None

def GetDistributionSettings():
    """Get distribution settings from user"""
    settings = {}

    # Main distribution method
    dist_options = ["FillCurve", "FixedSpacing", "FixedCount"]
    dist_method = rs.GetString("Distribution method", "FillCurve", dist_options)
    if not dist_method:
        return None

    if dist_method == "FillCurve":
        # For filling entire curve, ask for count and distribution type
        settings['count'] = rs.GetInteger("Number of blocks to distribute", 10, 2, 1000)
        if settings['count'] is None:
            return None

        # Distribution type within fill curve
        dist_type = rs.GetString("Distribution type", "Even", ["Even", "Random"])
        if not dist_type:
            return None
        settings['distribution_type'] = dist_type
        settings['distribution_method'] = 'fill_curve'

    elif dist_method == "FixedSpacing":
        # Fixed spacing between objects
        settings['spacing'] = rs.GetReal("Distance between blocks", 1.0, 0.01)
        if settings['spacing'] is None:
            return None

        # Ask for variation
        vary_type = rs.GetString("Spacing variation", "None", ["None", "Random"])
        if not vary_type:
            return None

        if vary_type == "Random":
            settings['spacing_variation'] = rs.GetReal("Variation range (+/-)", 0.2, 0.0, settings['spacing'] * 0.9)
            if settings['spacing_variation'] is None:
                return None
        else:
            settings['spacing_variation'] = 0.0

        settings['distribution_method'] = 'fixed_spacing'

    else:  # FixedCount
        settings['count'] = rs.GetInteger("Number of blocks", 10, 1, 1000)
        if settings['count'] is None:
            return None

        settings['spacing'] = rs.GetReal("Distance between blocks", 1.0, 0.01)
        if settings['spacing'] is None:
            return None

        placement = rs.GetString("Placement", "Start", ["Start", "Center", "End"])
        if not placement:
            return None
        settings['placement'] = placement.lower()
        settings['distribution_method'] = 'fixed_count'

    # Scale settings
    scale_type = rs.GetString("Scale variation", "Random", ["None", "Random"])
    if not scale_type:
        return None

    if scale_type == "Random":
        settings['min_scale'] = rs.GetReal("Minimum scale (1.0 = original)", 0.8, 0.01)
        if settings['min_scale'] is None:
            return None
        settings['max_scale'] = rs.GetReal("Maximum scale (1.0 = original)", 1.2, settings['min_scale'])
        if settings['max_scale'] is None:
            return None
    else:
        settings['min_scale'] = 1.0
        settings['max_scale'] = 1.0

    # Rotation settings
    rotation_type = rs.GetString("Rotation", "Random", ["None", "Random"])
    if not rotation_type:
        return None
    settings['random_rotation'] = (rotation_type == "Random")

    # Alignment options
    alignment = rs.GetString("Orientation", "FollowCurve", ["FollowCurve", "Original"])
    if not alignment:
        return None
    settings['align_to_curve'] = (alignment == "FollowCurve")

    return settings

def DistributeBlocksAlongCurve(blocks, curve, settings):
    """Main function to distribute blocks along curve"""

    if not blocks or not curve or not settings:
        return False

    # Get curve domain and length
    curve_domain = curve.Domain
    curve_length = curve.GetLength()

    # Calculate positions along curve based on distribution method
    positions = []

    if settings['distribution_method'] == 'fill_curve':
        # Distribute count evenly or randomly along entire curve
        if settings['distribution_type'] == 'Random':
            # Generate random positions and sort them
            for i in range(settings['count']):
                pos = random.uniform(0, curve_length)
                positions.append(pos)
            positions.sort()
        else:  # Even
            # Even distribution along entire curve
            if settings['count'] > 1:
                step = curve_length / (settings['count'] - 1)
                for i in range(settings['count']):
                    positions.append(i * step)
            else:
                positions.append(0)

    elif settings['distribution_method'] == 'fixed_spacing':
        # Use fixed spacing with optional variation
        current_pos = 0
        while current_pos <= curve_length:
            positions.append(current_pos)

            # Calculate next spacing
            spacing = settings['spacing']
            if settings['spacing_variation'] > 0:
                spacing += random.uniform(-settings['spacing_variation'], settings['spacing_variation'])

            current_pos += spacing

    else:  # fixed_count
        # Place fixed number with fixed spacing
        total_length = (settings['count'] - 1) * settings['spacing']

        if settings['placement'] == 'center':
            # Center the distribution on the curve
            start_pos = (curve_length - total_length) / 2.0
            if start_pos < 0:
                start_pos = 0
        elif settings['placement'] == 'end':
            # Start from the end
            start_pos = curve_length - total_length
            if start_pos < 0:
                start_pos = 0
        else:  # start
            start_pos = 0

        for i in range(settings['count']):
            pos = start_pos + (i * settings['spacing'])
            if pos >= 0 and pos <= curve_length:
                positions.append(pos)

    # Create block instances
    created_instances = []

    for pos in positions:
        # Get parameter at length
        success, t = curve.LengthParameter(pos)
        if not success:
            continue

        # Get point and frame at parameter
        point = curve.PointAt(t)
        success, frame = curve.FrameAt(t)
        if not success:
            continue

        # Select random block
        block_def = random.choice(blocks)

        # Create transformation matrix
        transform = Rhino.Geometry.Transform.Identity

        # First, move to origin if aligning to curve
        if settings['align_to_curve']:
            # Get curve tangent at this point
            tangent = curve.TangentAt(t)

            # Create a plane that keeps Z up but aligns X with the curve tangent
            # This ensures objects stay upright (trees, people, cars don't flip)
            z_axis = Rhino.Geometry.Vector3d.ZAxis
            x_axis = tangent
            x_axis.Z = 0  # Project tangent to XY plane
            x_axis.Unitize()

            # If the tangent is vertical, use world X axis
            if x_axis.Length < 0.001:
                x_axis = Rhino.Geometry.Vector3d.XAxis

            # Create Y axis perpendicular to X and Z
            y_axis = Rhino.Geometry.Vector3d.CrossProduct(z_axis, x_axis)

            # Create the target plane
            target_plane = Rhino.Geometry.Plane(point, x_axis, y_axis)
            source_plane = Rhino.Geometry.Plane.WorldXY

            transform = Rhino.Geometry.Transform.PlaneToPlane(source_plane, target_plane)
        else:
            # Just translate to position
            transform = Rhino.Geometry.Transform.Translation(point.X, point.Y, point.Z)

        # Apply random rotation around Z if requested
        if settings['random_rotation']:
            angle = random.uniform(0, 2 * math.pi)
            # Always rotate around world Z axis to keep objects upright
            rot_transform = Rhino.Geometry.Transform.Rotation(angle, Rhino.Geometry.Vector3d.ZAxis, point)
            transform = rot_transform * transform

        # Apply scaling with random range
        scale_factor = random.uniform(settings['min_scale'], settings['max_scale'])

        if scale_factor != 1.0:
            scale_transform = Rhino.Geometry.Transform.Scale(point, scale_factor)
            transform = scale_transform * transform

        # Create instance
        instance_id = sc.doc.Objects.AddInstanceObject(block_def.Index, transform)
        if instance_id != System.Guid.Empty:
            created_instances.append(instance_id)

    return created_instances

def main():
    """Main script execution"""

    # Get blocks to distribute
    print("Select blocks to distribute...")
    blocks = SelectBlocks()
    if not blocks:
        print("No blocks selected")
        return

    print("Selected {} block definition(s)".format(len(blocks)))

    # Get curve
    print("Select curve...")
    curve = SelectCurve()
    if not curve:
        print("No curve selected")
        return

    # Get settings
    print("Configure distribution settings...")
    settings = GetDistributionSettings()
    if not settings:
        print("Operation cancelled")
        return

    # Distribute blocks
    rs.EnableRedraw(False)

    created = DistributeBlocksAlongCurve(blocks, curve, settings)

    rs.EnableRedraw(True)

    if created:
        print("Created {} block instances".format(len(created)))
        # Select the created instances
        rs.SelectObjects(created)
    else:
        print("Failed to create block instances")

# Run the script
if __name__ == "__main__":
    main()
