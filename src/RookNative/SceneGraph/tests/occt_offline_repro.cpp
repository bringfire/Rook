// occt_offline_repro.cpp
//
// STANDALONE OFFLINE ASan repro harness for the OcctAdjacencyEngine::Evaluate
// stack-corruption bug. NO Rhino, NO httplib. Reads SpatialTest.3dm via
// openNURBS, extracts the SAME source + 5 candidate ON_Breps the plugin sees,
// builds ObjectBrepPayloads, and calls the REAL engine path
// (OcctAdjacencyEngine().Evaluate(...)) — the exact in-plugin code, compiled
// with /fsanitize=address. ASan names the OOB write file:line in one run.
//
// This is a DIAGNOSTIC tool. It does NOT change engine logic.

// openNURBS standalone: it ships as a DLL, so we must declare its classes
// __declspec(dllimport) (same rationale as OnBrepToOcct.cpp) to avoid LNK2005
// from locally-emitted template instantiations.
#ifndef NOMINMAX
#define NOMINMAX 1
#endif
#ifndef OPENNURBS_IMPORTS
#define OPENNURBS_IMPORTS
#endif
#include "opennurbs.h"

#include "SceneGraph/OcctAdjacencyTypes.h"
#include "SceneGraph/OcctAdjacencyEngine.h"

#include <cstdio>
#include <vector>
#include <string>
#include <memory>

// Read the model, find a ModelGeometry object by GUID string, return an owned
// deep-copy ON_Brep (or null). Extrusions are converted to Brep form.
static std::unique_ptr<const ON_Brep> GetBrep(const ONX_Model& model, const char* guid) {
    ON_UUID want = ON_UuidFromString(guid);
    ONX_ModelComponentIterator it(model, ON_ModelComponent::Type::ModelGeometry);
    for (const ON_ModelComponent* c = it.FirstComponent(); c; c = it.NextComponent()) {
        const ON_ModelGeometryComponent* g = ON_ModelGeometryComponent::Cast(c);
        if (!g) continue;
        const ON_3dmObjectAttributes* attr = g->Attributes(nullptr);
        ON_UUID have = attr ? attr->m_uuid : ON_nil_uuid;
        if (ON_UuidCompare(have, want) != 0) continue;
        const ON_Geometry* geo = g->Geometry(nullptr);
        if (!geo) return nullptr;
        if (const ON_Brep* b = ON_Brep::Cast(geo))
            return std::unique_ptr<const ON_Brep>(new ON_Brep(*b));
        if (const ON_Extrusion* e = ON_Extrusion::Cast(geo)) {
            ON_Brep* bf = e->BrepForm();
            if (bf) return std::unique_ptr<const ON_Brep>(bf);
        }
        return nullptr;  // matched id but not a Brep/Extrusion
    }
    return nullptr;
}

int main() {
    ON::Begin();

    ONX_Model model;
    const wchar_t* path = L"C:\\Models\\SpatialTest.3dm"  // any local test model;
    if (!model.Read(path)) {
        printf("READ FAIL: %ls\n", path);
        ON::End();
        return 2;
    }

    auto mk = [&](const char* g) {
        Rook::occt::ObjectBrepPayload p;
        p.objectId = g;
        p.modelUnitsToMillimeters = 25.4;  // inches
        p.brep = GetBrep(model, g);
        p.capability = p.brep ? Rook::occt::Capability::ExactBrep
                              : Rook::occt::Capability::FailedWithDiagnostics;
        return p;
    };

    Rook::occt::ObjectBrepPayload source = mk("08d4dedf-1387-453a-9938-7f3ab516b8ac");
    printf("source brep=%p\n", (void*)source.brep.get());

    const char* cg[] = {
        "71065f57-ee93-4af5-8a67-9aa1c4e88302",
        "5c12cc83-5fe3-4f2c-9fca-c0575c9f5dd3",
        "be0ca730-f3e9-4b41-a5bf-6b3848607b14",
        "7e80db98-d133-4a05-b9fe-ee6d37d9069d",
        "26b2c012-24cf-4656-9e48-8083dc072cad",
    };
    std::vector<Rook::occt::ObjectBrepPayload> cands;
    for (auto g : cg) {
        Rook::occt::ObjectBrepPayload p = mk(g);
        printf("cand %s brep=%p\n", g, (void*)p.brep.get());
        cands.push_back(std::move(p));
    }

    double tol = 1e-2 / 25.4;  // fuzzMm / modelUnitsToMillimeters
    printf("calling Evaluate... tol=%.8f\n", tol);
    fflush(stdout);

    Rook::occt::ExactAdjacencyCore core =
        Rook::occt::OcctAdjacencyEngine().Evaluate(source, cands, tol);

    printf("DONE edges=%zu cap-check survived\n", core.edges.size());
    for (auto& e : core.edges)
        printf("  edge -> %s area=%.3f facePairs=%zu\n",
               e.targetId.c_str(), e.sharedArea, e.facePairs.size());

    ON::End();
    return 0;
}
