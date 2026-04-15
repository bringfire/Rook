// RookBlockBasePointUserData.cs — Rook-owned symmetric UserData slot for
// storing a block definition's authored basePoint. Managed mirror of
// src/RookNative/UserData/RookBlockBasePointUserData.{h,cpp}. See design doc:
// docs/plans/2026-04-15-block-basepoint-metadata-userdata-migration-design.md
//
// The [Guid(...)] attribute MUST match the native kRookBlockBasePointUserDataId
// constant bit-for-bit. Binary serialization MUST match the native
// Write/Read implementation (same chunk typecode, same major/minor version,
// same field order + widths) — RhinoCommon's UserData loader dispatches
// incoming archived UserData to registered managed types by GUID, then
// invokes Read with a BinaryArchiveReader positioned at the payload.

using System;
using System.Runtime.InteropServices;
using Rhino.DocObjects;
using Rhino.DocObjects.Custom;
using Rhino.FileIO;
using Rhino.Geometry;

namespace Rook.UserData
{
    [Guid("0CD9F899-C9AA-4FC5-8F45-E081409245E9")]
    public class RookBlockBasePointUserData : Rhino.DocObjects.Custom.UserData
    {
        // Must match native TCODE_ANONYMOUS_CHUNK == TCODE_USER | TCODE_CRC
        //                                        == 0x40000000 | 0x8000
        //                                        == 0x40008000.
        private const uint TcodeAnonymousChunk = 0x40008000u;

        public Point3d BasePoint { get; set; } = Point3d.Origin;

        public override string Description => "Rook block basePoint metadata";

        public override bool ShouldWrite => true;  // persist to .3dm

        protected override void OnDuplicate(Rhino.DocObjects.Custom.UserData source)
        {
            if (source is RookBlockBasePointUserData other)
                BasePoint = other.BasePoint;
            // Else: OnDuplicate called with wrong type — shouldn't happen.
        }

        protected override bool Write(BinaryArchiveWriter archive)
        {
            if (!archive.BeginWrite3dmChunk(TcodeAnonymousChunk, 1, 0))
                return false;

            try
            {
                archive.WriteDouble(BasePoint.X);
                archive.WriteDouble(BasePoint.Y);
                archive.WriteDouble(BasePoint.Z);
            }
            catch
            {
                archive.EndWrite3dmChunk();
                return false;
            }

            return archive.EndWrite3dmChunk();
        }

        protected override bool Read(BinaryArchiveReader archive)
        {
            if (!archive.BeginRead3dmChunk(TcodeAnonymousChunk, out int major, out int minor))
                return false;

            bool ok = true;
            try
            {
                if (major == 1)
                {
                    double x = archive.ReadDouble();
                    double y = archive.ReadDouble();
                    double z = archive.ReadDouble();
                    BasePoint = new Point3d(x, y, z);
                }
                else
                {
                    // Unknown major: forward-compat, treat slot as missing.
                    // Caller falls back to legacy user-string per §4.1.
                    ok = false;
                }
            }
            catch
            {
                ok = false;
            }

            // EndRead3dmChunk(bool) — pass false to suppress CRC warnings when
            // we bailed early (unknown major / exception). Return the combined
            // success flag.
            bool endOk = archive.EndRead3dmChunk(ok);
            return ok && endOk;
        }

        // ---- Scoped helpers — InstanceDefinition only, no generic overload.
        //
        // Attach removes any pre-existing instance first, then attaches a
        // fresh one. Guarantees the "exactly one authoritative payload"
        // invariant from §3.1 of the design doc.

        public static bool Attach(InstanceDefinition idef, Point3d basePoint)
        {
            if (idef == null) return false;

            Remove(idef);  // detach any pre-existing instance first

            var ud = new RookBlockBasePointUserData { BasePoint = basePoint };
            return idef.UserData.Add(ud);
        }

        public static bool TryRead(InstanceDefinition idef, out Point3d basePoint)
        {
            basePoint = Point3d.Origin;
            if (idef == null) return false;

            var ud = idef.UserData.Find(typeof(RookBlockBasePointUserData))
                as RookBlockBasePointUserData;
            if (ud == null) return false;

            basePoint = ud.BasePoint;
            return true;
        }

        public static bool Remove(InstanceDefinition idef)
        {
            if (idef == null) return false;

            // Loop until no matching payload remains. Guarantees the "exactly
            // one authoritative payload" invariant from §3.1 even if the idef
            // somehow ended up with duplicates (defensive against edge cases
            // where parent duplication or archive-read could leave more than
            // one instance attached).
            bool removedAny = false;
            while (true)
            {
                var ud = idef.UserData.Find(typeof(RookBlockBasePointUserData));
                if (ud == null) break;
                if (idef.UserData.Remove(ud))
                    removedAny = true;
                else
                    break;  // avoid infinite loop on pathological state
            }
            return removedAny;
        }
    }
}
