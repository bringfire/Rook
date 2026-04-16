// RookBlockBasePointUserData.h — Rook-owned symmetric UserData slot for
// storing a block definition's authored basePoint. See design doc:
// docs/plans/2026-04-15-block-basepoint-metadata-userdata-migration-design.md
//
// This is the first custom ON_UserData subclass in Rook. It exists so
// native and managed can agree on a persistent, public-API-accessible
// metadata slot on ON_InstanceDefinition for the PR #25 / #27 / #28 fix
// chain. The managed mirror lives at src/Rook/UserData/RookBlockBasePointUserData.cs
// and MUST carry the same [Guid(...)] value as the UUID constant below.

#pragma once

#include "stdafx.h"

class CRookBlockBasePointUserData : public ON_UserData
{
    ON_OBJECT_DECLARE(CRookBlockBasePointUserData);

public:
    CRookBlockBasePointUserData();
    CRookBlockBasePointUserData(const ON_3dPoint& basePoint);
    ~CRookBlockBasePointUserData() = default;

    // ON_Object / ON_UserData overrides — signatures match OpenNURBS SDK.
    bool Archive() const override;
    bool Write(ON_BinaryArchive& binary_archive) const override;
    bool Read(ON_BinaryArchive& binary_archive) override;
    bool GetDescription(ON_wString& description) override;

    // basePoint is definition metadata, not geometry in world space.
    // Do NOT apply object-level transforms to the stored payload.
    bool Transform(const ON_Xform& xform) override;

    // Payload.
    ON_3dPoint m_base_point = ON_3dPoint::Origin;

    // Scoped helpers — InstanceDefinition only, no generic ON_Object overload.
    // Attach removes any pre-existing instance first, then attaches a fresh
    // one, guaranteeing the "exactly one authoritative payload" invariant
    // from §3.1 of the design doc.
    static bool Attach(ON_InstanceDefinition& idef, const ON_3dPoint& basePoint);
    static bool TryRead(const ON_InstanceDefinition& idef, ON_3dPoint& out);
    static bool Remove(ON_InstanceDefinition& idef);
};

// Rook-owned UUID for this metadata slot. MUST match the C# mirror's
// [Guid(...)] attribute value bit-for-bit. Generated for issue #28.
// {0CD9F899-C9AA-4FC5-8F45-E081409245E9}
extern const ON_UUID kRookBlockBasePointUserDataId;
