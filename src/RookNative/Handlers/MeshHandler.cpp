// MeshHandler.cpp
//
// 12 mesh routes. Mesh primitives create breps first then mesh them.
// Reduce and QuadRemesh use RunScript (no direct SDK API).
// Boolean, smooth, weld, unweld use Rhino global functions.

#include "stdafx.h"
#include "Handlers/MeshHandler.h"
#include "Infrastructure/UndoScope.h"
#include "Infrastructure/JsonHelpers.h"
#include "Infrastructure/WriteResult.h"
#include "Infrastructure/ObjectDiffTracker.h"
#include "Models/DocumentHelpers.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

#include <limits>
#include <set>

namespace Rook {
namespace Handlers {

// ─── Helpers ────────────────────────────────────────────────────────

namespace
{
    constexpr int kDefaultMaxObjects = 8;
    constexpr int kDefaultMaxSourceVertices = 200000;
    constexpr int kDefaultMaxSourceTriangles = 300000;
    constexpr long long kDefaultMaxEstimatedJsonBytes = 50000000LL;

    struct Mesh2SplatCaps
    {
        int maxObjects = kDefaultMaxObjects;
        int maxSourceVertices = kDefaultMaxSourceVertices;
        int maxSourceTriangles = kDefaultMaxSourceTriangles;
        long long maxEstimatedJsonBytes = kDefaultMaxEstimatedJsonBytes;
    };

    struct Mesh2SplatCandidate
    {
        ON_UUID id = ON_nil_uuid;
        std::string idString;
        std::string name;
        int materialIndex = -1;
        std::string materialSource;
        int vertexCount = 0;
        long long triangleCount = 0;
        const ON_Mesh* mesh = nullptr;
    };

    static long long SaturatingSizeToInt64(size_t value)
    {
        const size_t maxValue = static_cast<size_t>((std::numeric_limits<long long>::max)());
        return value > maxValue
            ? (std::numeric_limits<long long>::max)()
            : static_cast<long long>(value);
    }

    static size_t SaturatingAddSize(size_t a, size_t b)
    {
        return b > (std::numeric_limits<size_t>::max)() - a
            ? (std::numeric_limits<size_t>::max)()
            : a + b;
    }

    static long long EstimateMesh2SplatJsonBytes(
        size_t objectCount,
        size_t materialCount,
        long long sourceVertexCount,
        long long sourceTriangleCount,
        size_t stringBytes)
    {
        long long estimate = 0;
        auto add = [&estimate](long long value)
        {
            if (value > (std::numeric_limits<long long>::max)() - estimate)
                estimate = (std::numeric_limits<long long>::max)();
            else
                estimate += value;
        };
        auto addScaled = [&add](long long scale, long long count)
        {
            if (count > (std::numeric_limits<long long>::max)() / scale)
                add((std::numeric_limits<long long>::max)());
            else
                add(scale * count);
        };

        addScaled(4096LL, SaturatingSizeToInt64(objectCount));
        addScaled(2048LL, SaturatingSizeToInt64(materialCount));
        addScaled(96LL, sourceVertexCount);
        addScaled(24LL, sourceTriangleCount);
        add(SaturatingSizeToInt64(stringBytes));
        return estimate;
    }

    static int GetPositiveIntCap(
        const nlohmann::json& body,
        const char* key,
        int defaultValue)
    {
        if (!body.contains(key))
            return defaultValue;
        if (!body[key].is_number_integer())
            throw std::invalid_argument(std::string("'") + key + "' must be a positive integer");

        const long long value = body[key].get<long long>();
        if (value <= 0 || value > static_cast<long long>((std::numeric_limits<int>::max)()))
            throw std::invalid_argument(std::string("'") + key + "' must be a positive integer");
        return static_cast<int>(value);
    }

    static long long GetPositiveInt64Cap(
        const nlohmann::json& body,
        const char* key,
        long long defaultValue)
    {
        if (!body.contains(key))
            return defaultValue;
        if (!body[key].is_number_integer())
            throw std::invalid_argument(std::string("'") + key + "' must be a positive integer");

        const long long value = body[key].get<long long>();
        if (value <= 0)
            throw std::invalid_argument(std::string("'") + key + "' must be a positive integer");
        return value;
    }

    static nlohmann::json ColorToJson(const ON_Color& color)
    {
        const double alphaOpacity = 1.0 - (static_cast<double>(color.Alpha()) / 255.0);

        nlohmann::json j;
        j["r"] = static_cast<int>(color.Red());
        j["g"] = static_cast<int>(color.Green());
        j["b"] = static_cast<int>(color.Blue());
        j["a"] = static_cast<int>(std::round(alphaOpacity * 255.0));
        j["rScalar"] = static_cast<double>(color.Red()) / 255.0;
        j["gScalar"] = static_cast<double>(color.Green()) / 255.0;
        j["bScalar"] = static_cast<double>(color.Blue()) / 255.0;
        j["aScalar"] = alphaOpacity;
        return j;
    }

    static nlohmann::json Point3fToJson(const ON_3fPoint& point)
    {
        return nlohmann::json::array({ point.x, point.y, point.z });
    }

    static nlohmann::json Vector3fToJson(const ON_3fVector& vector)
    {
        return nlohmann::json::array({ vector.x, vector.y, vector.z });
    }

    static nlohmann::json Uv2fToJson(const ON_2fPoint& uv)
    {
        return nlohmann::json::array({ uv.x, uv.y });
    }

    static nlohmann::json XformToJson(const ON_Xform& xform)
    {
        nlohmann::json rows = nlohmann::json::array();
        for (int r = 0; r < 4; ++r)
        {
            nlohmann::json row = nlohmann::json::array();
            for (int c = 0; c < 4; ++c)
                row.push_back(xform[r][c]);
            rows.push_back(std::move(row));
        }
        return rows;
    }

    static std::string MaterialSourceToString(ON::object_material_source source)
    {
        switch (source)
        {
        case ON::material_from_object: return "MaterialFromObject";
        case ON::material_from_layer: return "MaterialFromLayer";
        case ON::material_from_parent: return "MaterialFromParent";
        default: return "MaterialSourceUnknown";
        }
    }

    static std::string TextureTypeToString(ON_Texture::TYPE type)
    {
        switch (type)
        {
        case ON_Texture::TYPE::bitmap_texture: return "bitmap_texture";
        case ON_Texture::TYPE::bump_texture: return "bump_texture";
        case ON_Texture::TYPE::transparency_texture: return "transparency_texture";
        case ON_Texture::TYPE::emap_texture: return "emap_texture";
        default: return "texture_type_" + std::to_string(static_cast<unsigned int>(type));
        }
    }

    static int ResolveEffectiveMaterialIndex(CRhinoDoc* pDoc, const CRhinoObject* obj)
    {
        const auto& attrs = obj->Attributes();
        if (attrs.MaterialSource() == ON::material_from_object)
            return attrs.m_material_index;

        if (attrs.MaterialSource() == ON::material_from_layer)
        {
            const int layerIndex = attrs.m_layer_index;
            if (layerIndex >= 0 && layerIndex < pDoc->m_layer_table.LayerCount())
                return pDoc->m_layer_table[layerIndex].RenderMaterialIndex();
        }

        return attrs.m_material_index;
    }

    static bool CountMeshTriangles(
        const ON_Mesh* mesh,
        long long& triangleCount,
        std::string& error)
    {
        triangleCount = 0;
        if (!mesh)
        {
            error = "Object geometry is not a mesh";
            return false;
        }

        if (mesh->HasNgons())
        {
            error = "Mesh contains ngons; mesh2splat capture currently supports triangle and quad mesh faces only";
            return false;
        }

        const int vertexCount = mesh->VertexCount();
        for (int i = 0; i < mesh->FaceCount(); ++i)
        {
            const ON_MeshFace& face = mesh->m_F[i];
            if (face.IsTriangle())
            {
                if (face.vi[0] < 0 || face.vi[1] < 0 || face.vi[2] < 0
                    || face.vi[0] >= vertexCount || face.vi[1] >= vertexCount || face.vi[2] >= vertexCount)
                {
                    error = "Mesh contains an invalid triangle face";
                    return false;
                }
                ++triangleCount;
            }
            else if (face.IsQuad())
            {
                if (face.vi[0] < 0 || face.vi[1] < 0 || face.vi[2] < 0 || face.vi[3] < 0
                    || face.vi[0] >= vertexCount || face.vi[1] >= vertexCount
                    || face.vi[2] >= vertexCount || face.vi[3] >= vertexCount)
                {
                    error = "Mesh contains an invalid quad face";
                    return false;
                }
                triangleCount += 2;
            }
            else
            {
                error = "Mesh contains a face that is neither triangle nor quad";
                return false;
            }
        }

        if (triangleCount <= 0)
        {
            error = "Mesh contains no triangle faces";
            return false;
        }

        return true;
    }

    static std::string BuildSkipReason(const CRhinoObject* obj)
    {
        if (!obj)
            return "Object not found";
        if (obj->IsDeleted())
            return "Object is deleted";
        if (obj->IsHidden())
            return "Object is hidden";
        if (obj->IsReference())
            return "Object is from a reference model";
        if (obj->IsLocked())
            return "Object is locked";
        if (ON_Mesh::Cast(obj->Geometry()) == nullptr)
            return "Object is not a mesh";
        return "";
    }

    static nlohmann::json SerializeMaterialMetadata(
        CRhinoDoc* pDoc,
        int matIndex,
        size_t& stringBytes)
    {
        const CRhinoMaterial& mat = pDoc->m_material_table[matIndex];
        const std::string name = WideToUtf8(mat.Name());
        stringBytes += name.size();

        ON_Color diffuse = mat.Diffuse();
        ON_Color specular = mat.Specular();
        ON_Color emission = mat.Emission();

        nlohmann::json textures = nlohmann::json::array();
        for (int i = 0; i < mat.m_textures.Count(); ++i)
        {
            const ON_Texture& texture = mat.m_textures[i];
            nlohmann::json tex;
            tex["index"] = i;
            tex["type"] = static_cast<unsigned int>(texture.m_type);
            tex["typeName"] = TextureTypeToString(texture.m_type);
            tex["enabled"] = texture.m_bOn;
            tex["mappingChannel"] = texture.m_mapping_channel_id;

            const std::string fullPath = WideToUtf8(texture.m_image_file_reference.FullPath());
            const std::string relativePath = WideToUtf8(texture.m_image_file_reference.RelativePath());
            if (!fullPath.empty())
            {
                tex["fullPath"] = fullPath;
                stringBytes += fullPath.size();
            }
            if (!relativePath.empty())
            {
                tex["relativePath"] = relativePath;
                stringBytes += relativePath.size();
            }
            tex["pathMetadataOnly"] = true;
            textures.push_back(std::move(tex));
        }

        nlohmann::json j;
        j["index"] = matIndex;
        j["id"] = UuidToString(mat.Id());
        j["name"] = name;
        j["diffuseColor"] = ColorToJson(diffuse);
        j["baseColor"] = ColorToJson(diffuse);
        j["baseColorSource"] = "legacyDiffuse";
        j["specularColor"] = ColorToJson(specular);
        j["emissionColor"] = ColorToJson(emission);
        j["reflectivity"] = mat.Reflectivity();
        j["transparency"] = mat.Transparency();
        j["shine"] = mat.Shine();
        j["hasTexture"] = mat.m_textures.Count() > 0 || mat.TextureBitmap() != nullptr;
        j["textures"] = std::move(textures);
        return j;
    }

    static nlohmann::json SerializeMeshObject(const Mesh2SplatCandidate& candidate)
    {
        const ON_Mesh* mesh = candidate.mesh;
        const int vertexCount = mesh->VertexCount();
        const bool hasNormals = mesh->HasVertexNormals() && mesh->m_N.Count() == vertexCount;
        const bool hasUvs = mesh->HasTextureCoordinates() && mesh->m_T.Count() == vertexCount;

        nlohmann::json vertices = nlohmann::json::array();
        for (int i = 0; i < vertexCount; ++i)
            vertices.push_back(Point3fToJson(mesh->m_V[i]));

        nlohmann::json normals = nlohmann::json::array();
        if (hasNormals)
        {
            for (int i = 0; i < vertexCount; ++i)
                normals.push_back(Vector3fToJson(mesh->m_N[i]));
        }

        nlohmann::json uvs = nlohmann::json::array();
        if (hasUvs)
        {
            for (int i = 0; i < vertexCount; ++i)
                uvs.push_back(Uv2fToJson(mesh->m_T[i]));
        }

        nlohmann::json faces = nlohmann::json::array();
        for (int i = 0; i < mesh->FaceCount(); ++i)
        {
            const ON_MeshFace& face = mesh->m_F[i];
            if (face.IsTriangle())
            {
                faces.push_back(nlohmann::json::array({ face.vi[0], face.vi[1], face.vi[2] }));
            }
            else
            {
                faces.push_back(nlohmann::json::array({ face.vi[0], face.vi[1], face.vi[2] }));
                faces.push_back(nlohmann::json::array({ face.vi[0], face.vi[2], face.vi[3] }));
            }
        }

        nlohmann::json materialAssignment;
        materialAssignment["scope"] = "object";
        materialAssignment["materialIndex"] = candidate.materialIndex;
        materialAssignment["materialSource"] = candidate.materialSource;
        materialAssignment["perFaceMaterialsSupported"] = false;

        nlohmann::json transformDiagnostics;
        transformDiagnostics["worldSpaceVertices"] = true;
        transformDiagnostics["objectSpaceEqualsWorldSpace"] = true;
        transformDiagnostics["localToWorldApplied"] = false;
        transformDiagnostics["localToWorld"] = XformToJson(ON_Xform::IdentityTransformation);
        transformDiagnostics["note"] = "Captured from Rhino mesh object geometry coordinates; block instances are not expanded by this route.";

        nlohmann::json obj;
        obj["id"] = candidate.idString;
        obj["name"] = candidate.name;
        obj["materialIndex"] = candidate.materialIndex;
        obj["materialSource"] = candidate.materialSource;
        obj["materialAssignment"] = std::move(materialAssignment);
        obj["vertexCount"] = candidate.vertexCount;
        obj["triangleCount"] = candidate.triangleCount;
        obj["sourceFaceCount"] = mesh->FaceCount();
        obj["sourceTriangleFaceCount"] = mesh->TriangleCount();
        obj["sourceQuadFaceCount"] = mesh->QuadCount();
        obj["normalsValid"] = hasNormals;
        obj["uvChannel"] = 1;
        obj["uvValid"] = hasUvs;
        obj["uvSource"] = hasUvs ? "mesh.m_T" : "";
        obj["vertices"] = std::move(vertices);
        obj["normals"] = std::move(normals);
        obj["uvs"] = std::move(uvs);
        obj["faces"] = std::move(faces);
        obj["transformDiagnostics"] = std::move(transformDiagnostics);
        return obj;
    }
}

static const ON_Brep* ExtractBrep(const ON_Geometry* geom, bool& bMustDelete)
{
    bMustDelete = false;

    if (const ON_Brep* brep = ON_Brep::Cast(geom))
        return brep;

    if (const ON_Extrusion* ext = ON_Extrusion::Cast(geom))
    {
        ON_Brep* brep = ext->BrepForm();
        if (brep) { bMustDelete = true; return brep; }
    }

    if (const ON_Surface* srf = ON_Surface::Cast(geom))
    {
        ON_Brep* brep = srf->BrepForm();
        if (brep) { bMustDelete = true; return brep; }
    }

    return nullptr;
}

// Mesh a brep with given parameters, returns a joined mesh (caller owns).
static ON_Mesh* MeshBrep(const ON_Brep& brep, const ON_MeshParameters& mp)
{
    ON_SimpleArray<ON_Mesh*> meshList;
    int count = brep.CreateMesh(mp, meshList);
    if (count == 0 || meshList.Count() == 0)
        return nullptr;

    // Join all face meshes into one
    ON_Mesh* result = meshList[0];
    for (int i = 1; i < meshList.Count(); ++i)
    {
        if (meshList[i])
        {
            result->Append(*meshList[i]);
            delete meshList[i];
        }
    }
    return result;
}

// ─── POST /mesh2splat/capture ─────────────────────────────────────

void HandleMesh2SplatCapture(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    Mesh2SplatCaps caps;
    std::vector<ON_UUID> explicitIds;
    bool hasExplicitIds = false;
    bool allowPartial = false;

    auto sendStructuredError = [&](const std::string& code, const std::string& message)
    {
        nlohmann::json err;
        err["code"] = code;
        err["message"] = message;
        err["retryable"] = false;
        CRookServer::SendErrorData(res, err);
    };

    try
    {
        allowPartial = body.value("allowPartial", false);
        caps.maxObjects = GetPositiveIntCap(body, "maxObjects", kDefaultMaxObjects);
        caps.maxSourceVertices = GetPositiveIntCap(body, "maxSourceVertices", kDefaultMaxSourceVertices);
        caps.maxSourceTriangles = GetPositiveIntCap(body, "maxSourceTriangles", kDefaultMaxSourceTriangles);
        caps.maxEstimatedJsonBytes = GetPositiveInt64Cap(body, "maxEstimatedJsonBytes", kDefaultMaxEstimatedJsonBytes);

        if (body.contains("object_ids"))
        {
            if (!body["object_ids"].is_array())
            {
                sendStructuredError(
                    "invalid_object_id",
                    "'object_ids' must be an array of UUID strings");
                return;
            }
            try
            {
                explicitIds = ParseUuids(body, "object_ids");
            }
            catch (const std::exception& ex)
            {
                sendStructuredError("invalid_object_id", ex.what());
                return;
            }
            hasExplicitIds = true;
        }
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, allowPartial, caps, hasExplicitIds, explicitIds = std::move(explicitIds)]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        nlohmann::json warnings = nlohmann::json::array();
        nlohmann::json errors = nlohmann::json::array();
        std::vector<Mesh2SplatCandidate> candidates;
        std::set<int> materialIndices;

        size_t totalStringBytes = 0;
        long long sourceVertexCount = 0;
        long long sourceTriangleCount = 0;
        bool captureTooLarge = false;
        std::string tooLargeMessage;
        long long tooLargeEstimatedJsonBytes = 0;
        long long tooLargeObjectCount = 0;
        long long tooLargeSourceVertexCount = 0;
        long long tooLargeSourceTriangleCount = 0;
        long long tooLargeMaterialCount = 0;

        auto addWarning = [&](const std::string& message)
        {
            warnings.push_back(message);
            totalStringBytes = SaturatingAddSize(totalStringBytes, message.size());
        };

        auto addError = [&](const std::string& idString, const std::string& message, const std::string& code)
        {
            nlohmann::json e;
            e["id"] = idString;
            e["code"] = code;
            e["message"] = message;
            errors.push_back(std::move(e));
            totalStringBytes = SaturatingAddSize(totalStringBytes, idString.size());
            totalStringBytes = SaturatingAddSize(totalStringBytes, message.size());
            totalStringBytes = SaturatingAddSize(totalStringBytes, code.size());
        };

        auto makeCaptureFailure = [&](
            const std::string& code,
            const std::string& message) -> WriteResult
        {
            WriteResult wr;
            wr.success = false;
            wr.data["code"] = code;
            wr.data["message"] = message;
            wr.data["errors"] = std::move(errors);
            wr.data["warnings"] = std::move(warnings);
            return wr;
        };

        auto makeTooLarge = [&](
            const std::string& message,
            long long estimatedJsonBytes,
            long long objectCount,
            long long vertexCount,
            long long triangleCount,
            long long materialCount) -> WriteResult
        {
            WriteResult wr;
            wr.success = false;
            wr.data["code"] = "capture_too_large";
            wr.data["message"] = message;
            wr.data["estimatedJsonBytes"] = estimatedJsonBytes;
            wr.data["objectCount"] = objectCount;
            wr.data["sourceVertexCount"] = vertexCount;
            wr.data["sourceTriangleCount"] = triangleCount;
            wr.data["materialCount"] = materialCount;
            wr.data["caps"] = {
                {"maxObjects", caps.maxObjects},
                {"maxSourceVertices", caps.maxSourceVertices},
                {"maxSourceTriangles", caps.maxSourceTriangles},
                {"maxEstimatedJsonBytes", caps.maxEstimatedJsonBytes}
            };
            wr.data["warnings"] = std::move(warnings);
            return wr;
        };

        auto recordTooLarge = [&](
            const std::string& message,
            long long estimatedJsonBytes,
            long long objectCount,
            long long vertexCount,
            long long triangleCount,
            long long materialCount)
        {
            captureTooLarge = true;
            tooLargeMessage = message;
            tooLargeEstimatedJsonBytes = estimatedJsonBytes;
            tooLargeObjectCount = objectCount;
            tooLargeSourceVertexCount = vertexCount;
            tooLargeSourceTriangleCount = triangleCount;
            tooLargeMaterialCount = materialCount;
        };

        auto addCandidate = [&](const CRhinoObject* obj, bool explicitRequest)
        {
            const std::string idString = obj ? UuidToString(obj->Attributes().m_uuid) : "";
            std::string skipReason = BuildSkipReason(obj);
            if (!skipReason.empty())
            {
                if (explicitRequest && !allowPartial)
                    addError(idString, skipReason, "unsupported_requested_object");
                else
                    addWarning(idString.empty() ? skipReason : (idString + ": " + skipReason));
                return;
            }

            const ON_Mesh* mesh = ON_Mesh::Cast(obj->Geometry());
            long long triangleCount = 0;
            std::string meshError;
            if (!CountMeshTriangles(mesh, triangleCount, meshError))
            {
                if (explicitRequest && !allowPartial)
                    addError(idString, meshError, "unsupported_requested_object");
                else
                    addWarning(idString + ": " + meshError);
                return;
            }

            Mesh2SplatCandidate candidate;
            candidate.id = obj->Attributes().m_uuid;
            candidate.idString = idString;
            candidate.name = WideToUtf8(obj->Attributes().m_name);
            candidate.materialIndex = ResolveEffectiveMaterialIndex(pDoc, obj);
            candidate.materialSource = MaterialSourceToString(obj->Attributes().MaterialSource());
            candidate.vertexCount = mesh->VertexCount();
            candidate.triangleCount = triangleCount;
            candidate.mesh = mesh;

            const long long nextObjectCount = SaturatingSizeToInt64(candidates.size()) + 1LL;
            const long long nextSourceVertexCount = sourceVertexCount + static_cast<long long>(candidate.vertexCount);
            const long long nextSourceTriangleCount = sourceTriangleCount + static_cast<long long>(candidate.triangleCount);
            size_t candidateStringBytes = candidate.idString.size();
            candidateStringBytes = SaturatingAddSize(candidateStringBytes, candidate.name.size());
            candidateStringBytes = SaturatingAddSize(candidateStringBytes, candidate.materialSource.size());
            const size_t nextStringBytes = SaturatingAddSize(totalStringBytes, candidateStringBytes);

            bool includesNewMaterial = false;
            if (candidate.materialIndex >= 0
                && candidate.materialIndex < pDoc->m_material_table.MaterialCount()
                && !pDoc->m_material_table[candidate.materialIndex].IsDeleted()
                && materialIndices.find(candidate.materialIndex) == materialIndices.end())
            {
                includesNewMaterial = true;
            }

            const size_t nextMaterialCount = materialIndices.size() + (includesNewMaterial ? 1 : 0);
            const long long nextEstimatedJsonBytes = EstimateMesh2SplatJsonBytes(
                candidates.size() + 1,
                nextMaterialCount,
                nextSourceVertexCount,
                nextSourceTriangleCount,
                nextStringBytes);

            if (nextObjectCount > static_cast<long long>(caps.maxObjects))
            {
                recordTooLarge(
                    "Capture exceeds maxObjects",
                    nextEstimatedJsonBytes,
                    nextObjectCount,
                    nextSourceVertexCount,
                    nextSourceTriangleCount,
                    SaturatingSizeToInt64(nextMaterialCount));
                return;
            }
            if (nextSourceVertexCount > static_cast<long long>(caps.maxSourceVertices))
            {
                recordTooLarge(
                    "Capture exceeds maxSourceVertices",
                    nextEstimatedJsonBytes,
                    nextObjectCount,
                    nextSourceVertexCount,
                    nextSourceTriangleCount,
                    SaturatingSizeToInt64(nextMaterialCount));
                return;
            }
            if (nextSourceTriangleCount > static_cast<long long>(caps.maxSourceTriangles))
            {
                recordTooLarge(
                    "Capture exceeds maxSourceTriangles",
                    nextEstimatedJsonBytes,
                    nextObjectCount,
                    nextSourceVertexCount,
                    nextSourceTriangleCount,
                    SaturatingSizeToInt64(nextMaterialCount));
                return;
            }
            if (nextEstimatedJsonBytes > caps.maxEstimatedJsonBytes)
            {
                recordTooLarge(
                    "Capture exceeds maxEstimatedJsonBytes",
                    nextEstimatedJsonBytes,
                    nextObjectCount,
                    nextSourceVertexCount,
                    nextSourceTriangleCount,
                    SaturatingSizeToInt64(nextMaterialCount));
                return;
            }

            totalStringBytes = nextStringBytes;
            sourceVertexCount = nextSourceVertexCount;
            sourceTriangleCount = nextSourceTriangleCount;

            if (candidate.materialIndex >= 0
                && candidate.materialIndex < pDoc->m_material_table.MaterialCount()
                && !pDoc->m_material_table[candidate.materialIndex].IsDeleted())
            {
                materialIndices.insert(candidate.materialIndex);
            }

            candidates.push_back(std::move(candidate));
        };

        if (hasExplicitIds)
        {
            for (const auto& id : explicitIds)
            {
                const CRhinoObject* obj = pDoc->LookupObject(id);
                if (!obj)
                {
                    const std::string idString = UuidToString(id);
                    if (allowPartial)
                        addWarning(idString + ": Object not found");
                    else
                        addError(idString, "Object not found", "invalid_object_id");
                    continue;
                }

                addCandidate(obj, true);
                if (captureTooLarge)
                    break;
            }
        }
        else
        {
            int selectedObjectCount = 0;
            CRhinoObjectIterator it(*pDoc,
                CRhinoObjectIterator::undeleted_objects,
                CRhinoObjectIterator::active_objects);

            for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
            {
                if (!obj->IsSelected(true))
                    continue;
                ++selectedObjectCount;
                addCandidate(obj, false);
                if (captureTooLarge)
                    break;
            }
            if (selectedObjectCount == 0 && !captureTooLarge)
            {
                return makeCaptureFailure(
                    "selection_required",
                    "Select at least one mesh object or provide object_ids");
            }
        }

        if (captureTooLarge)
        {
            return makeTooLarge(
                tooLargeMessage,
                tooLargeEstimatedJsonBytes,
                tooLargeObjectCount,
                tooLargeSourceVertexCount,
                tooLargeSourceTriangleCount,
                tooLargeMaterialCount);
        }

        if (!errors.empty())
        {
            const std::string code = errors.front().value("code", "capture_failed");
            return makeCaptureFailure(
                code,
                "One or more requested mesh objects could not be captured");
        }

        if (candidates.empty())
        {
            return makeCaptureFailure(
                "no_supported_meshes",
                "No supported mesh objects were captured");
        }

        nlohmann::json materials = nlohmann::json::array();
        for (int matIndex : materialIndices)
            materials.push_back(SerializeMaterialMetadata(pDoc, matIndex, totalStringBytes));

        const long long estimatedJsonBytes = EstimateMesh2SplatJsonBytes(
            candidates.size(),
            materialIndices.size(),
            sourceVertexCount,
            sourceTriangleCount,
            totalStringBytes);

        if (estimatedJsonBytes > caps.maxEstimatedJsonBytes)
        {
            return makeTooLarge(
                "Capture exceeds maxEstimatedJsonBytes",
                estimatedJsonBytes,
                SaturatingSizeToInt64(candidates.size()),
                sourceVertexCount,
                sourceTriangleCount,
                SaturatingSizeToInt64(materialIndices.size()));
        }

        const ON_3dmUnitsAndTolerances& ut = pDoc->Properties().ModelUnitsAndTolerances();
        const ON::LengthUnitSystem unitSystem = ut.m_unit_system.UnitSystem();
        const double unitScaleToMeters = ON::UnitScale(unitSystem, ON::LengthUnitSystem::Meters);

        nlohmann::json objects = nlohmann::json::array();
        for (const auto& candidate : candidates)
            objects.push_back(SerializeMeshObject(candidate));

        WriteResult wr;
        wr.success = true;
        wr.data["documentUnits"] = WideToUtf8(ut.m_unit_system.ToString());
        wr.data["unitScaleToMeters"] = unitScaleToMeters;
        wr.data["estimatedJsonBytes"] = estimatedJsonBytes;
        wr.data["objectCount"] = static_cast<int>(candidates.size());
        wr.data["sourceObjectCount"] = static_cast<int>(candidates.size());
        if (hasExplicitIds)
            wr.data["requestedObjectCount"] = static_cast<int>(explicitIds.size());
        else
            wr.data["requestedObjectCount"] = nullptr;
        wr.data["sourceVertexCount"] = sourceVertexCount;
        wr.data["sourceTriangleCount"] = sourceTriangleCount;
        wr.data["materialCount"] = static_cast<int>(materialIndices.size());
        wr.data["caps"] = {
            {"maxObjects", caps.maxObjects},
            {"maxSourceVertices", caps.maxSourceVertices},
            {"maxSourceTriangles", caps.maxSourceTriangles},
            {"maxEstimatedJsonBytes", caps.maxEstimatedJsonBytes}
        };
        wr.data["objects"] = std::move(objects);
        wr.data["materials"] = std::move(materials);
        wr.data["warnings"] = std::move(warnings);
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /mesh/from-brep ────────────────────────────────────────

void HandleMeshFromBrep(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID brepId;
    try { brepId = ParseUuid(body, "brepId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    double density = body.value("density", 0.0);
    double minEdge = body.value("minEdgeLength", 0.0);
    double maxEdge = body.value("maxEdgeLength", 0.0);
    bool jagged = body.value("jagged", false);
    bool simple = body.value("simple", false);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, brepId, density, minEdge, maxEdge, jagged, simple]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Mesh from brep");

        const CRhinoObject* obj = pDoc->LookupObject(brepId);
        if (!obj)
            throw std::invalid_argument("Brep object not found");

        bool bMustDelete = false;
        const ON_Brep* brep = ExtractBrep(obj->Geometry(), bMustDelete);
        std::unique_ptr<const ON_Brep> brepGuard(bMustDelete ? brep : nullptr);
        if (!brep)
            throw std::invalid_argument("Object is not a brep/extrusion/surface");

        ON_MeshParameters mp;
        if (simple)
        {
            mp = ON_MeshParameters::FastRenderMesh;
        }
        else
        {
            mp = ON_MeshParameters::QualityRenderMesh;
            if (density > 0.0) mp.SetRelativeTolerance(density);
            if (minEdge > 0.0) mp.SetMinimumEdgeLength(minEdge);
            if (maxEdge > 0.0) mp.SetMaximumEdgeLength(maxEdge);
            mp.SetJaggedSeams(jagged);
        }

        ON_Mesh* mesh = MeshBrep(*brep, mp);
        if (!mesh)
            throw std::invalid_argument("Meshing failed — geometry may be invalid");

        ON_3dmObjectAttributes attrs = obj->Attributes();
        CRhinoMeshObject* newObj = pDoc->AddMeshObject(*mesh, &attrs);
        ON_UUID resultId = newObj ? newObj->Attributes().m_uuid : ON_nil_uuid;
        int vCount = mesh->VertexCount();
        int fCount = mesh->FaceCount();
        delete mesh;

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(resultId);
        wr.data["vertexCount"] = vCount;
        wr.data["faceCount"] = fCount;

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /mesh/box ──────────────────────────────────────────────

void HandleMeshBox(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("width") || !body.contains("depth") || !body.contains("height"))
    {
        CRookServer::SendError(res, "Missing 'width', 'depth', or 'height'");
        return;
    }

    ON_3dPoint origin = ParsePoint3dOrDefault(body, "origin", ON_3dPoint::Origin);
    double width = body["width"].get<double>();
    double depth = body["depth"].get<double>();
    double height = body["height"].get<double>();
    int xCount = body.value("xCount", 1);
    int yCount = body.value("yCount", 1);
    int zCount = body.value("zCount", 1);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, origin, width, depth, height, xCount, yCount, zCount]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Mesh box");

        // Build box from 8 corners, then mesh it
        ON_3dPoint corners[8];
        corners[0] = origin;
        corners[1] = origin + ON_3dVector(width, 0, 0);
        corners[2] = origin + ON_3dVector(width, depth, 0);
        corners[3] = origin + ON_3dVector(0, depth, 0);
        corners[4] = origin + ON_3dVector(0, 0, height);
        corners[5] = origin + ON_3dVector(width, 0, height);
        corners[6] = origin + ON_3dVector(width, depth, height);
        corners[7] = origin + ON_3dVector(0, depth, height);

        ON_Brep* brep = ON_BrepBox(corners);
        if (!brep)
            throw std::invalid_argument("Failed to create box brep");
        std::unique_ptr<ON_Brep> brepGuard(brep);

        ON_MeshParameters mp = ON_MeshParameters::QualityRenderMesh;
        ON_Mesh* mesh = MeshBrep(*brep, mp);
        if (!mesh)
            throw std::invalid_argument("Failed to mesh box");

        CRhinoMeshObject* newObj = pDoc->AddMeshObject(*mesh);
        ON_UUID resultId = newObj ? newObj->Attributes().m_uuid : ON_nil_uuid;
        int vCount = mesh->VertexCount();
        int fCount = mesh->FaceCount();
        delete mesh;

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(resultId);
        wr.data["vertexCount"] = vCount;
        wr.data["faceCount"] = fCount;

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /mesh/sphere ───────────────────────────────────────────

void HandleMeshSphere(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("radius"))
    {
        CRookServer::SendError(res, "Missing 'radius'");
        return;
    }

    ON_3dPoint center = ParsePoint3dOrDefault(body, "center", ON_3dPoint::Origin);
    double radius = body["radius"].get<double>();
    int rings = (std::max)(3, body.value("rings", 10));
    int segments = (std::max)(3, body.value("segments", 10));

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, center, radius, rings, segments]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Mesh sphere");

        // Create sphere brep, then mesh with appropriate density
        ON_Sphere sphere(center, radius);
        ON_Brep* brep = ON_BrepSphere(sphere);
        if (!brep)
            throw std::invalid_argument("Failed to create sphere brep");
        std::unique_ptr<ON_Brep> brepGuard(brep);

        // Adjust mesh params based on rings/segments
        ON_MeshParameters mp = ON_MeshParameters::QualityRenderMesh;
        mp.SetGridMinCount(rings);
        mp.SetGridMaxCount(segments * rings);

        ON_Mesh* mesh = MeshBrep(*brep, mp);
        if (!mesh)
            throw std::invalid_argument("Failed to mesh sphere");

        CRhinoMeshObject* newObj = pDoc->AddMeshObject(*mesh);
        ON_UUID resultId = newObj ? newObj->Attributes().m_uuid : ON_nil_uuid;
        int vCount = mesh->VertexCount();
        int fCount = mesh->FaceCount();
        delete mesh;

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(resultId);
        wr.data["vertexCount"] = vCount;
        wr.data["faceCount"] = fCount;

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /mesh/cylinder ─────────────────────────────────────────

void HandleMeshCylinder(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("radius") || !body.contains("height"))
    {
        CRookServer::SendError(res, "Missing 'radius' or 'height'");
        return;
    }

    ON_3dPoint center = ParsePoint3dOrDefault(body, "center", ON_3dPoint::Origin);
    double radius = body["radius"].get<double>();
    double height = body["height"].get<double>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, center, radius, height]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Mesh cylinder");

        ON_Plane basePlane(center, ON_3dVector::ZAxis);
        ON_Circle circle(basePlane, radius);
        ON_Cylinder cylinder(circle, height);

        ON_Brep* brep = ON_BrepCylinder(cylinder, true, true);
        if (!brep)
            throw std::invalid_argument("Failed to create cylinder brep");
        std::unique_ptr<ON_Brep> brepGuard(brep);

        ON_MeshParameters mp = ON_MeshParameters::QualityRenderMesh;
        ON_Mesh* mesh = MeshBrep(*brep, mp);
        if (!mesh)
            throw std::invalid_argument("Failed to mesh cylinder");

        CRhinoMeshObject* newObj = pDoc->AddMeshObject(*mesh);
        ON_UUID resultId = newObj ? newObj->Attributes().m_uuid : ON_nil_uuid;
        int vCount = mesh->VertexCount();
        int fCount = mesh->FaceCount();
        delete mesh;

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(resultId);
        wr.data["vertexCount"] = vCount;
        wr.data["faceCount"] = fCount;

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /mesh/cone ─────────────────────────────────────────────

void HandleMeshCone(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("radius") || !body.contains("height"))
    {
        CRookServer::SendError(res, "Missing 'radius' or 'height'");
        return;
    }

    ON_3dPoint center = ParsePoint3dOrDefault(body, "center", ON_3dPoint::Origin);
    double radius = body["radius"].get<double>();
    double height = body["height"].get<double>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, center, radius, height]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Mesh cone");

        ON_Plane basePlane(center, ON_3dVector::ZAxis);
        ON_Cone cone(basePlane, height, radius);

        ON_Brep* brep = ON_BrepCone(cone, true);
        if (!brep)
            throw std::invalid_argument("Failed to create cone brep");
        std::unique_ptr<ON_Brep> brepGuard(brep);

        ON_MeshParameters mp = ON_MeshParameters::QualityRenderMesh;
        ON_Mesh* mesh = MeshBrep(*brep, mp);
        if (!mesh)
            throw std::invalid_argument("Failed to mesh cone");

        CRhinoMeshObject* newObj = pDoc->AddMeshObject(*mesh);
        ON_UUID resultId = newObj ? newObj->Attributes().m_uuid : ON_nil_uuid;
        int vCount = mesh->VertexCount();
        int fCount = mesh->FaceCount();
        delete mesh;

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(resultId);
        wr.data["vertexCount"] = vCount;
        wr.data["faceCount"] = fCount;

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /mesh/boolean ──────────────────────────────────────────

void HandleMeshBoolean(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("operation") || !body["operation"].is_string())
    {
        CRookServer::SendError(res, "Missing 'operation' (union|difference|intersection)");
        return;
    }

    std::string operation = body["operation"].get<std::string>();
    if (!IEquals(operation, "union") && !IEquals(operation, "difference") &&
        !IEquals(operation, "intersection"))
    {
        CRookServer::SendError(res, "Unknown operation. Use: union, difference, intersection");
        return;
    }

    std::vector<ON_UUID> meshIds;
    try { meshIds = ParseUuids(body, "meshIds"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    if (meshIds.size() < 2)
    {
        CRookServer::SendError(res, "Need at least 2 mesh IDs");
        return;
    }

    bool deleteInputs = body.value("deleteInputs", true);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, operation, meshIds = std::move(meshIds), deleteInputs]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Mesh boolean");
        double tol = pDoc->AbsoluteTolerance();

        // Collect mesh pointers
        ON_SimpleArray<const ON_Mesh*> allMeshes;
        for (const auto& uuid : meshIds)
        {
            const CRhinoObject* obj = pDoc->LookupObject(uuid);
            if (!obj)
                throw std::invalid_argument("Mesh not found: " + UuidToString(uuid));
            const ON_Mesh* mesh = ON_Mesh::Cast(obj->Geometry());
            if (!mesh)
                throw std::invalid_argument("Object is not a mesh: " + UuidToString(uuid));
            allMeshes.Append(mesh);
        }

        ON_SimpleArray<ON_Mesh*> outMeshes;
        bool happened = false;

        if (IEquals(operation, "union"))
        {
            RhinoMeshBooleanUnion(allMeshes, tol, tol, &happened, outMeshes);
        }
        else
        {
            // Difference and intersection: first mesh vs rest
            ON_SimpleArray<const ON_Mesh*> set0, set1;
            set0.Append(allMeshes[0]);
            for (int i = 1; i < allMeshes.Count(); ++i)
                set1.Append(allMeshes[i]);

            if (IEquals(operation, "difference"))
                RhinoMeshBooleanDifference(set0, set1, tol, tol, &happened, outMeshes);
            else
                RhinoMeshBooleanIntersection(set0, set1, tol, tol, &happened, outMeshes);
        }

        if (!happened || outMeshes.Count() == 0)
        {
            for (int i = 0; i < outMeshes.Count(); ++i)
                delete outMeshes[i];

            WriteResult wr;
            wr.success = false;
            wr.data["error"] = "Mesh boolean " + operation + " produced no result";
            return wr;
        }

        nlohmann::json resultIds = nlohmann::json::array();
        for (int i = 0; i < outMeshes.Count(); ++i)
        {
            if (outMeshes[i])
            {
                CRhinoMeshObject* newObj = pDoc->AddMeshObject(*outMeshes[i]);
                if (newObj)
                    resultIds.push_back(UuidToString(newObj->Attributes().m_uuid));
                delete outMeshes[i];
                outMeshes[i] = nullptr;
            }
        }

        if (deleteInputs)
        {
            for (const auto& uuid : meshIds)
            {
                const CRhinoObject* obj = pDoc->LookupObject(uuid);
                if (obj)
                    pDoc->DeleteObject(CRhinoObjRef(obj));
            }
        }

        WriteResult wr;
        wr.success = true;
        wr.data["operation"] = operation;
        wr.data["resultCount"] = static_cast<int>(resultIds.size());
        wr.data["resultIds"] = std::move(resultIds);

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /mesh/reduce ───────────────────────────────────────────

void HandleMeshReduce(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID meshId;
    try { meshId = ParseUuid(body, "meshId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    if (!body.contains("targetCount") || !body["targetCount"].is_number_integer())
    {
        CRookServer::SendError(res, "Missing 'targetCount' integer");
        return;
    }

    int targetCount = body["targetCount"].get<int>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, meshId, targetCount]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Reduce mesh");

        const CRhinoObject* obj = pDoc->LookupObject(meshId);
        if (!obj)
            throw std::invalid_argument("Mesh object not found");
        const ON_Mesh* mesh = ON_Mesh::Cast(obj->Geometry());
        if (!mesh)
            throw std::invalid_argument("Object is not a mesh");

        int originalFaces = mesh->FaceCount();

        // Select the mesh and use RunScript (no direct API for mesh reduce)
        CRhinoObjectIterator clearIt(*pDoc,
            CRhinoObjectIterator::normal_or_locked_objects,
            CRhinoObjectIterator::active_objects);
        for (const CRhinoObject* o = clearIt.First(); o; o = clearIt.Next())
            const_cast<CRhinoObject*>(o)->Select(false);

        const_cast<CRhinoObject*>(obj)->Select(true);

        ON_wString cmd;
        cmd.Format(L"_-ReduceMesh _PolygonCount=%d _Enter _Enter", targetCount);

        RhinoApp().RunScript(pDoc->RuntimeSerialNumber(),
            static_cast<const wchar_t*>(cmd), 0);

        // Re-fetch: command may modify in-place (same UUID) or create new object
        ON_UUID resultId = meshId;
        const CRhinoObject* newObj = pDoc->LookupObject(meshId);
        if (!newObj)
        {
            // UUID changed — find by diff tracker would be ideal but
            // ReduceMesh almost always modifies in-place. Fall back to error.
            throw std::invalid_argument("Mesh was deleted during reduce");
        }

        const ON_Mesh* newMesh = ON_Mesh::Cast(newObj->Geometry());
        if (!newMesh)
            throw std::invalid_argument("Object is no longer a mesh after reduce");

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(resultId);
        wr.data["originalFaceCount"] = originalFaces;
        wr.data["newFaceCount"] = newMesh->FaceCount();
        wr.data["vertexCount"] = newMesh->VertexCount();

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /mesh/quad-remesh ──────────────────────────────────────

void HandleMeshQuadRemesh(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID meshId;
    try { meshId = ParseUuid(body, "meshId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    int targetQuadCount = body.value("targetQuadCount", 1000);
    bool adaptive = body.value("adaptive", true);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, meshId, targetQuadCount, adaptive]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"QuadRemesh");

        const CRhinoObject* obj = pDoc->LookupObject(meshId);
        if (!obj)
            throw std::invalid_argument("Mesh object not found");
        const ON_Mesh* mesh = ON_Mesh::Cast(obj->Geometry());
        if (!mesh)
            throw std::invalid_argument("Object is not a mesh");

        // Use RunScript (no direct QuadRemesh API in C++ SDK)
        CRhinoObjectIterator clearIt(*pDoc,
            CRhinoObjectIterator::normal_or_locked_objects,
            CRhinoObjectIterator::active_objects);
        for (const CRhinoObject* o = clearIt.First(); o; o = clearIt.Next())
            const_cast<CRhinoObject*>(o)->Select(false);

        const_cast<CRhinoObject*>(obj)->Select(true);

        ON_wString cmd;
        const wchar_t* adaptiveStr = adaptive ? L"Yes" : L"No";
        cmd.Format(L"_-QuadRemesh _TargetQuadCount=%d _AdaptiveQuadCount=%s _Enter",
                   targetQuadCount, adaptiveStr);

        ObjectDiffTracker tracker(pDoc);
        RhinoApp().RunScript(pDoc->RuntimeSerialNumber(),
            static_cast<const wchar_t*>(cmd), 0);

        std::vector<ON_UUID> newIds = tracker.GetNewObjects();

        // If we got new objects, the original was replaced
        ON_UUID resultId = meshId;
        int fCount = 0, vCount = 0;

        if (!newIds.empty())
        {
            resultId = newIds[0];
            const CRhinoObject* newObj = pDoc->LookupObject(resultId);
            if (newObj)
            {
                const ON_Mesh* newMesh = ON_Mesh::Cast(newObj->Geometry());
                if (newMesh) { fCount = newMesh->FaceCount(); vCount = newMesh->VertexCount(); }
            }
        }
        else
        {
            // Original may have been modified in-place
            const CRhinoObject* reObj = pDoc->LookupObject(meshId);
            if (reObj)
            {
                const ON_Mesh* reMesh = ON_Mesh::Cast(reObj->Geometry());
                if (reMesh) { fCount = reMesh->FaceCount(); vCount = reMesh->VertexCount(); }
            }
        }

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(resultId);
        wr.data["faceCount"] = fCount;
        wr.data["vertexCount"] = vCount;

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /mesh/repair ───────────────────────────────────────────

void HandleMeshRepair(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID meshId;
    try { meshId = ParseUuid(body, "meshId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    bool fillHoles = body.value("fillHoles", true);
    bool rebuildNormals = body.value("rebuildNormals", true);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, meshId, fillHoles, rebuildNormals]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Repair mesh");

        const CRhinoObject* obj = pDoc->LookupObject(meshId);
        if (!obj)
            throw std::invalid_argument("Mesh object not found");
        const ON_Mesh* mesh = ON_Mesh::Cast(obj->Geometry());
        if (!mesh)
            throw std::invalid_argument("Object is not a mesh");

        ON_Mesh* newMesh = new ON_Mesh(*mesh);
        if (!newMesh)
            throw std::invalid_argument("Failed to duplicate mesh");

        nlohmann::json repairs = nlohmann::json::array();

        // Repair using RhinoRepairMesh
        double tol = pDoc->AbsoluteTolerance();
        if (RhinoRepairMesh(newMesh, tol))
            repairs.push_back("Repaired mesh");

        if (rebuildNormals)
        {
            newMesh->ComputeVertexNormals();
            repairs.push_back("Rebuilt normals");
        }

        // Unify normals
        ON_Mesh* unified = RhinoUnifyMeshNormals(*newMesh);
        if (unified && unified != newMesh)
        {
            delete newMesh;
            newMesh = unified;
            repairs.push_back("Unified normals");
        }
        else if (unified == newMesh)
        {
            repairs.push_back("Normals already unified");
        }

        newMesh->Compact();
        repairs.push_back("Compacted mesh");

        pDoc->ReplaceObject(CRhinoObjRef(obj), *newMesh);
        int vCount = newMesh->VertexCount();
        int fCount = newMesh->FaceCount();
        bool isValid = newMesh->IsValid();
        delete newMesh;

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(meshId);
        wr.data["repairs"] = std::move(repairs);
        wr.data["faceCount"] = fCount;
        wr.data["vertexCount"] = vCount;
        wr.data["isValid"] = isValid;

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /mesh/smooth ───────────────────────────────────────────

void HandleMeshSmooth(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID meshId;
    try { meshId = ParseUuid(body, "meshId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    double factor = body.value("factor", 0.5);
    factor = (std::max)(0.0, (std::min)(1.0, factor));
    int iterations = body.value("iterations", 1);
    iterations = (std::max)(1, (std::min)(100, iterations));

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, meshId, factor, iterations]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Smooth mesh");

        const CRhinoObject* obj = pDoc->LookupObject(meshId);
        if (!obj)
            throw std::invalid_argument("Mesh object not found");
        const ON_Mesh* mesh = ON_Mesh::Cast(obj->Geometry());
        if (!mesh)
            throw std::invalid_argument("Object is not a mesh");

        // RhinoSmoothMesh with numSteps
        ON_Mesh* smoothed = RhinoSmoothMesh(mesh, factor, iterations,
            true, true, true,  // x, y, z smoothing
            true,              // fix boundaries
            0,                 // world coordinate system
            nullptr);          // no custom plane

        if (!smoothed)
            throw std::invalid_argument("Mesh smoothing failed");

        pDoc->ReplaceObject(CRhinoObjRef(obj), *smoothed);
        int vCount = smoothed->VertexCount();
        int fCount = smoothed->FaceCount();
        delete smoothed;

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(meshId);
        wr.data["factor"] = factor;
        wr.data["iterations"] = iterations;
        wr.data["vertexCount"] = vCount;
        wr.data["faceCount"] = fCount;

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /mesh/weld ─────────────────────────────────────────────

void HandleMeshWeld(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID meshId;
    try { meshId = ParseUuid(body, "meshId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    double angleDegrees = body.value("angle", 22.5);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, meshId, angleDegrees]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Weld mesh");

        const CRhinoObject* obj = pDoc->LookupObject(meshId);
        if (!obj)
            throw std::invalid_argument("Mesh object not found");
        const ON_Mesh* mesh = ON_Mesh::Cast(obj->Geometry());
        if (!mesh)
            throw std::invalid_argument("Object is not a mesh");

        int origVerts = mesh->VertexCount();

        // ON_Mesh::Weld() doesn't exist in SDK; use RunScript
        CRhinoObjectIterator clearIt(*pDoc,
            CRhinoObjectIterator::normal_or_locked_objects,
            CRhinoObjectIterator::active_objects);
        for (const CRhinoObject* o = clearIt.First(); o; o = clearIt.Next())
            const_cast<CRhinoObject*>(o)->Select(false);
        const_cast<CRhinoObject*>(obj)->Select(true);

        ON_wString cmd;
        cmd.Format(L"_-Weld _Angle=%g _Enter", angleDegrees);
        RhinoApp().RunScript(pDoc->RuntimeSerialNumber(),
            static_cast<const wchar_t*>(cmd), 0);

        // Re-fetch (object may have been replaced)
        const CRhinoObject* newObj = pDoc->LookupObject(meshId);
        const ON_Mesh* newMesh = newObj ? ON_Mesh::Cast(newObj->Geometry()) : nullptr;
        int newVerts = newMesh ? newMesh->VertexCount() : origVerts;
        int fCount = newMesh ? newMesh->FaceCount() : 0;

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(meshId);
        wr.data["angle"] = angleDegrees;
        wr.data["originalVertexCount"] = origVerts;
        wr.data["newVertexCount"] = newVerts;
        wr.data["faceCount"] = fCount;

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /mesh/unweld ───────────────────────────────────────────

void HandleMeshUnweld(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID meshId;
    try { meshId = ParseUuid(body, "meshId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    double angleDegrees = body.value("angle", 22.5);
    double angleRadians = angleDegrees * ON_PI / 180.0;

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, meshId, angleDegrees, angleRadians]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Unweld mesh");

        const CRhinoObject* obj = pDoc->LookupObject(meshId);
        if (!obj)
            throw std::invalid_argument("Mesh object not found");
        const ON_Mesh* mesh = ON_Mesh::Cast(obj->Geometry());
        if (!mesh)
            throw std::invalid_argument("Object is not a mesh");

        int origVerts = mesh->VertexCount();

        ON_Mesh* unwelded = RhinoUnWeldMesh(*mesh, angleRadians);
        if (!unwelded)
            throw std::invalid_argument("Unweld failed");

        pDoc->ReplaceObject(CRhinoObjRef(obj), *unwelded);
        int newVerts = unwelded->VertexCount();
        int fCount = unwelded->FaceCount();
        delete unwelded;

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(meshId);
        wr.data["angle"] = angleDegrees;
        wr.data["originalVertexCount"] = origVerts;
        wr.data["newVertexCount"] = newVerts;
        wr.data["faceCount"] = fCount;

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

} // namespace Handlers
} // namespace Rook
