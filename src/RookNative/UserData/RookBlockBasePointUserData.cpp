// RookBlockBasePointUserData.cpp — see header + design doc §3 for contract.

#include "stdafx.h"
#include "RookBlockBasePointUserData.h"

// Rook plugin UUID (from RookNativePlugin.cpp). Required to be non-nil on
// m_application_uuid; if nil, the UserData is NOT persisted to .3dm per
// OpenNURBS contract (see opennurbs_userdata.h on m_application_uuid).
// {A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906}
static const ON_UUID kRookNativeApplicationId =
    { 0xa38e0e8f, 0xe06e, 0x40d2, { 0xa6, 0xbd, 0x7e, 0xdb, 0xc2, 0xcb, 0x19, 0x06 } };

// {0CD9F899-C9AA-4FC5-8F45-E081409245E9}
const ON_UUID kRookBlockBasePointUserDataId =
    { 0x0cd9f899, 0xc9aa, 0x4fc5, { 0x8f, 0x45, 0xe0, 0x81, 0x40, 0x92, 0x45, 0xe9 } };

ON_OBJECT_IMPLEMENT(CRookBlockBasePointUserData, ON_UserData,
    "0CD9F899-C9AA-4FC5-8F45-E081409245E9");

// ---------------------------------------------------------------------------
// Constructors

CRookBlockBasePointUserData::CRookBlockBasePointUserData()
    : m_base_point(ON_3dPoint::Origin)
{
    m_userdata_uuid = kRookBlockBasePointUserDataId;
    m_application_uuid = kRookNativeApplicationId;
    m_userdata_copycount = 1;  // copied on parent duplication; required for OnDuplicate parity

    // Note on "not_transformed" semantic: Rhino 8's C++ OpenNURBS SDK does
    // NOT expose an `m_userdata_xformage` field or an `ON_UserData::not_transformed`
    // enum (confirmed via grep across the full SDK tree). The semantic is
    // expressed via our Transform() override below, which ignores the incoming
    // xform and returns true. Payload m_base_point is never derived from
    // m_userdata_xform, so the inherited xform-tracking state is inert here.
}

CRookBlockBasePointUserData::CRookBlockBasePointUserData(const ON_3dPoint& basePoint)
    : CRookBlockBasePointUserData()
{
    m_base_point = basePoint;
}

// ---------------------------------------------------------------------------
// ON_UserData overrides

bool CRookBlockBasePointUserData::Archive() const
{
    return true;  // persist to .3dm
}

bool CRookBlockBasePointUserData::Write(ON_BinaryArchive& binary_archive) const
{
    // Versioned chunk: major=1, minor=0. Bump major for breaking schema
    // changes; minor for additive. Readers that don't understand major
    // must fall through to the legacy user-string fallback (see §4.1).
    if (!binary_archive.BeginWrite3dmChunk(TCODE_ANONYMOUS_CHUNK, 1, 0))
        return false;

    bool ok = true;
    if (ok) ok = binary_archive.WriteDouble(m_base_point.x);
    if (ok) ok = binary_archive.WriteDouble(m_base_point.y);
    if (ok) ok = binary_archive.WriteDouble(m_base_point.z);

    if (!binary_archive.EndWrite3dmChunk())
        ok = false;
    return ok;
}

bool CRookBlockBasePointUserData::Read(ON_BinaryArchive& binary_archive)
{
    int major = 0, minor = 0;
    if (!binary_archive.BeginRead3dmChunk(TCODE_ANONYMOUS_CHUNK, &major, &minor))
        return false;

    bool ok = true;
    if (major == 1)
    {
        if (ok) ok = binary_archive.ReadDouble(&m_base_point.x);
        if (ok) ok = binary_archive.ReadDouble(&m_base_point.y);
        if (ok) ok = binary_archive.ReadDouble(&m_base_point.z);
    }
    else
    {
        // Unknown major: fall through silently. Per §4.1 read-failure
        // policy, unknown-major is forward-compat (newer build wrote a
        // schema this build doesn't understand), handled by treating the
        // slot as missing; caller falls back to legacy user-string.
        ok = false;
    }

    if (!binary_archive.EndRead3dmChunk())
        ok = false;
    return ok;
}

bool CRookBlockBasePointUserData::GetDescription(ON_wString& description)
{
    description = L"Rook block basePoint metadata";
    return true;
}

bool CRookBlockBasePointUserData::Transform(const ON_Xform& /*xform*/)
{
    // basePoint is definition metadata, not geometry in world space.
    // Return true to keep UserData attached (false would cause SDK to
    // discard us on object transforms). Do NOT update m_base_point —
    // the design doc's "not_transformed" semantic.
    return true;
}

// ---------------------------------------------------------------------------
// Scoped attach / read / remove helpers

bool CRookBlockBasePointUserData::Attach(
    ON_InstanceDefinition& idef, const ON_3dPoint& basePoint)
{
    // Detach any existing instance first — guarantees the "exactly one
    // authoritative payload" invariant from §3.1.
    Remove(idef);

    // AttachUserData takes ownership; on failure it returns false and the
    // caller is responsible for deleting. On success ownership transfers
    // to the parent ON_Object's userdata list.
    CRookBlockBasePointUserData* ud = new CRookBlockBasePointUserData(basePoint);
    if (idef.AttachUserData(ud))
        return true;

    delete ud;
    return false;
}

bool CRookBlockBasePointUserData::TryRead(
    const ON_InstanceDefinition& idef, ON_3dPoint& out)
{
    ON_UserData* ud = idef.GetUserData(kRookBlockBasePointUserDataId);
    if (!ud) return false;

    CRookBlockBasePointUserData* bp = CRookBlockBasePointUserData::Cast(ud);
    if (!bp) return false;  // type mismatch — someone else claimed our UUID

    out = bp->m_base_point;
    return true;
}

bool CRookBlockBasePointUserData::Remove(ON_InstanceDefinition& idef)
{
    // Loop until no matching payload remains. Guarantees the "exactly one
    // authoritative payload" invariant from §3.1 even if the idef somehow
    // ended up with duplicate payloads (defensive against SDK edge cases
    // where parent-object duplication or user-data-list concatenation
    // could leave more than one instance attached).
    bool removed_any = false;
    while (true)
    {
        ON_UserData* ud = idef.GetUserData(kRookBlockBasePointUserDataId);
        if (!ud) break;
        if (idef.DetachUserData(ud))
        {
            delete ud;
            removed_any = true;
        }
        else
        {
            // Detach failed — bail to avoid infinite loop on pathological state.
            break;
        }
    }
    return removed_any;
}
