# P5 Tencent Hunyuan3D-2 Direct Availability Audit

**Timebox:** 30 minutes (extended to ~50 minutes — extension justified by significant strategic finding: Tencent's direct API exposes substantially more functionality than the fal-ai/hunyuan-3d/v3.1/pro/image-to-3d endpoint we probed in P4).

## Audit Log

| Checked At | Source | Finding | Evidence |
|---|---|---|---|
| 2026-04-27 ~16:25 | Tencent Cloud API Explorer (https://console.tencentcloud.com/api/explorer) — Hunyuan service, version `v20230901` | Direct public API for Hunyuan3D-2 exists and is documented in Tencent's standard API Explorer interface | Browser exploration; full endpoint list captured below |
| 2026-04-27 ~16:30 | API Explorer SDK code-sample tab (Python) | Tencent provides an official Python SDK (`tencentcloud-sdk-python`) with typed request/response models per endpoint | Sample project downloaded to `docs/rook_docs/tencent_api_md/sample_python_75e13ea8-df6b-43d2-a3d8-71125b9a7f4e/` (gitignored); see `tencent_cloud_sample/sample.py` |
| 2026-04-27 ~16:35 | Tencent Cloud Quickstart PDF | International endpoint and account/key creation flow documented | Saved at `docs/rook_docs/tencent_api_md/1281_74125_en.pdf` (gitignored) |
| 2026-04-27 ~16:40 | Tencent Cloud API key console | Sub-user (CAM) key creation is the recommended path; root account API keys are explicitly discouraged via security warning dialog | Screenshot referenced in spike doc; root-account key creation deliberately NOT performed |
| 2026-04-27 ~16:50 | API Explorer endpoint list (left navigation) for Hunyuan 3D APIs | Seven endpoint pairs cover features absent from fal — including segmentation, smart topology, UV unwrapping, texture editing, and format conversion | Endpoint enumeration captured in this doc; cross-checked against P4's fal-ai/hunyuan-3d/v3.1/pro/image-to-3d schema (which exposes only the Pro tier) |

## Required Questions

### Does a direct public Tencent Hunyuan3D-2 API exist?

**Yes.** Tencent Cloud Hunyuan service, API version `v20230901`. The service exposes a standard Submit/Query lifecycle pattern (analogous to fal queue but with separate Submit/Query method pairs per job type) over typed SDK clients. International endpoint: `hunyuan.intl.tencentcloudapi.com`.

### What authentication model does it use?

**Paired credentials with TC3-HMAC-SHA256 request signing.**

- Two-part credentials: `SecretId` + `SecretKey`. Standard env-var names (per Tencent's official sample): `TENCENTCLOUD_SECRET_ID` and `TENCENTCLOUD_SECRET_KEY`.
- Optional ephemeral-credential support via STS Token (`credential.Credential("SecretId", "SecretKey", "Token")`).
- Signature computation handled invisibly by `tencentcloud-sdk-python`. No manual TC3-HMAC-SHA256 implementation required if the SDK is used.
- This is structurally different from the other providers in this spike:
  - fal.ai: `Authorization: Key <single-token>`
  - Replicate: `Authorization: Token <single-token>`
  - Gemini: `x-goog-api-key: <single-token>`
  - **Tencent: paired credentials + signed requests**

### Is pricing public?

**Documented, partially verified.** Tencent Cloud publishes pricing pages per service, but exact per-call rates for each Hunyuan3D endpoint were not pinned during this audit. Phase 4 kickoff should re-verify current pricing tables before any live call. (Pricing for the Pro tier was already captured indirectly via fal's resale at $0.375/call; Tencent direct should be at or below that since fal adds an aggregator margin.)

### Are live credentials immediately obtainable?

**No.** Obtaining usable credentials requires:

1. Tencent Cloud account in good standing (already exists for the operator)
2. CAM (Cloud Access Management) sub-user creation — Tencent's security warning correctly advised against using root-account API keys
3. Permission policy attached to the sub-user, scoped to the Hunyuan service (probably `QcloudHunyuanFullAccess` or a custom policy granting only the action verbs needed)
4. SecretId + SecretKey generation from the sub-user's credentials section

Estimated total setup time: **30–60 minutes** for someone unfamiliar with CAM, less if the operator has prior Tencent Cloud experience.

### Is a low-cost live call available now?

**Deferred.** The credential setup exceeds Phase 0's audit timebox, and the spike's gate is already satisfied without Tencent live evidence. Live integration is more efficiently performed at Phase 4 kickoff when there is concrete product surface to validate against.

## API Surface Captured

The complete Hunyuan 3D API surface visible in Tencent's API Explorer (as of 2026-04-27):

| Endpoint Pair | Capability | Available on fal? |
|---|---|---|
| `SubmitHunyuanTo3DProJob` / `QueryHunyuanTo3DProJob` | Pro-tier image-to-3D with optional 8-view input, configurable face count, optional PBR | ✅ (P4 probed this via `fal-ai/hunyuan-3d/v3.1/pro/image-to-3d`) |
| `SubmitHunyuanTo3DRapidJob` / `QueryHunyuanTo3DRapidJob` | Rapid tier — faster generation, lower quality | ❌ |
| `SubmitHunyuan3DPartJob` / `QueryHunyuan3DPartJob` | **Part segmentation** — split generated model into separate components | ❌ |
| `Submit3DSmartTopologyJob` / `Describe3DSmartTopologyJob` | **Smart retopology** — convert generated mesh to clean topology | ❌ |
| `SubmitHunyuanTo3DTextureEditJob` / `QueryHunyuanTo3DTextureEditJob` | **Texture editing** — modify generated textures | ❌ |
| `SubmitHunyuanTo3DUVJob` / `DescribeHunyuanTo3DUVJob` | **UV unwrapping** as a separate job (vs. fal where UVs are auto-generated and uncontrollable) | ❌ |
| `Convert3DFormat` / `SubmitConvert3DFormatJob` / `DescribeConvert3DFormatJob` | **Format conversion** between GLB / OBJ / FBX / USDZ / etc. | ❌ |

Cross-reference: P4's evidence at `.scratch/multi-provider-spike/captures/p4/` (and snapshot `p4_success/`) shows fal's Pro endpoint output already includes multiple format URLs (`model_urls.{glb, obj, fbx, mtl, texture, usdz}`), so format conversion is *partially* covered by fal's existing output. The other features (segmentation, retopology, UV editing, texture editing, rapid tier) have no fal equivalent.

## SDK Integration Facts (for Phase 4 reference)

From the downloaded SDK sample:

- **Package**: `tencentcloud-sdk-python` (single dependency; covers all Tencent Cloud services)
- **Module path**: `tencentcloud.hunyuan.v20230901` (versioned September 2023)
- **Client class**: `HunyuanClient` — single client handles all seven endpoint pairs
- **Request shape**: typed model classes per endpoint, e.g. `models.SubmitHunyuanTo3DProJobRequest`. Request fields populated via `req.from_json_string(json.dumps(params))` or direct attribute assignment.
- **Response shape**: typed response objects, e.g. `SubmitHunyuanTo3DProJobResponse`. Serialized via `resp.to_json_string()`.
- **Endpoint configuration**: `httpProfile.endpoint = "hunyuan.intl.tencentcloudapi.com"` for international users; region as second positional arg to `HunyuanClient` (empty string allowed; explicit values like `"ap-guangzhou"` or `"ap-singapore"` also accepted).
- **Exception type**: `tencentcloud.common.exception.tencent_cloud_sdk_exception.TencentCloudSDKException` — single typed error class for all SDK-level failures.
- **Auth**: `tencentcloud.common.credential.Credential(secret_id, secret_key)` for permanent credentials; three-arg form `Credential(secret_id, secret_key, token)` for STS ephemeral credentials.

## Outcome

**`complete`** — Tencent direct API documented and analyzed; SDK integration path identified; live API call deliberately deferred to Phase 4 to avoid duplicating CAM setup work.

## Strategic Note for Phase 1 / Phase 4

The advanced 3D features (segmentation, retopology, UV unwrapping, texture editing, rapid tier) that are absent from fal's Hunyuan3D Pro endpoint are exclusively available via Tencent direct on this catalog. **Any 3D product surface that requires clean topology, parts-based editing, controlled UV unwrapping, or fast-iteration previews cannot rely on fal alone and must include Tencent-direct integration.**

Phase 1 implications:

- **Decision 2 (capability schema):** the 3D capability flags must accommodate per-endpoint feature flags (`supports_part_segmentation`, `supports_smart_topology`, `supports_uv_editing`, `supports_texture_editing`, `supports_rapid_tier`, `output_format_conversion`). A flat "is 3D capable" boolean is insufficient; provider/route registration must declare which sub-capabilities are exposed.
- **Decision 4 (options codec):** Tencent direct introduces a fifth submission contract (paired credentials + SDK-typed models + Submit/Query method pair per job type), structurally different from fal/Replicate/Gemini. The options codec abstraction must accommodate SDK-mediated providers, not just raw HTTP shapes.
- **Decision 6 (secret-key namespace):** the secret store must support paired-credential providers (`SecretId` + `SecretKey`), not just single-token providers. Tencent is the first such provider in the spike's evidence set; Aliyun, AWS Bedrock, and other major cloud-AI providers are likely to follow the same pattern.
- **Phase 4 priority:** if 3D becomes a flagship product surface for Rook, Tencent direct should be the primary backend, with fal Hunyuan3D as the lighter/cheaper option for users who only need basic Pro-tier generation.

## Materials Saved (Local Only)

All saved under `docs/rook_docs/tencent_api_md/` (gitignored at `.gitignore:20` — these stay on the operator's machine and do not enter the repo):

- `1281_74125_en.pdf` — Tencent Cloud Quickstart guide
- `sample_python_75e13ea8-df6b-43d2-a3d8-71125b9a7f4e/` — official Tencent SDK Python sample for `SubmitHunyuanTo3DProJob`
  - `setup.py` — declares `tencentcloud-sdk-python` dependency
  - `tencent_cloud_sample/sample.py` — canonical invocation pattern (auth, client, request, response, exception)

The downloaded sample covers only the Pro endpoint, but the pattern generalizes verbatim to the other six endpoint pairs — Phase 4 won't need additional sample downloads.
