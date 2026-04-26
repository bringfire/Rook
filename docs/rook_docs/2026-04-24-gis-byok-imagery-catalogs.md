# GIS BYOK — Imagery + Meta-Catalog Gateways Dossier

**Part of:** [2026-04-24-gis-byok-pipeline-research.md](2026-04-24-gis-byok-pipeline-research.md)
**Status:** research (2026-04-24)

## Summary

**Microsoft Planetary Computer should anchor v1 of the BYOK pipeline.** It is STAC-native, ships a lightweight Python client (`pystac-client` + `planetary-computer` SAS signer), has no formal rate limits for public STAC search, carries no commercial-use restrictions on the core open datasets (Sentinel-1/2, Landsat, NAIP, Copernicus DEM, MS Buildings), and authenticates with a single free subscription key — a clean fit for a BYOK plugin. Google Earth Engine is a close second for *analysis*, but its April-2026 noncommercial-tier overhaul and explicit commercial split make it a poor default for a plugin that will mostly run inside paid architectural workflows. Direct-from-source providers (Copernicus Dataspace, USGS, NAIP-on-AWS) are wired up opportunistically as failover and for datasets Planetary Computer does not mirror.

## Imagery providers

### Sentinel-2 (Copernicus Dataspace Ecosystem)
- **Homepage:** https://dataspace.copernicus.eu
- **Coverage:** Global, 5-day revisit, 2015–present
- **Resolution:** 10 m (visible + NIR), 20 m (red-edge + SWIR), 60 m (atmospheric)
- **Auth:** Free account; OAuth2 token from `identity.dataspace.copernicus.eu`. SciHub (the legacy endpoint) was deprecated in late 2023 — Dataspace is the official successor.
- **License:** Copernicus free, full, open — commercial use permitted with attribution ("Contains modified Copernicus Sentinel data [Year]").
- **Rate limits:** Per-account quotas on OData download; the Sentinel Hub Process/Statistical APIs have a separate "Processing Unit" quota tied to account tier.
- **Python access:** `sentinelhub-py` (for Process/STAC APIs), `openeo` client, or raw OData/STAC via `pystac-client`. `sentinelsat` works against the old SciHub only — do not use.
- **Pipeline fit:** Preview + validation (footprint alignment over recent true-color mosaic).

### Sentinel-1 SAR (Copernicus Dataspace)
- Same auth / license / access as Sentinel-2.
- **Resolution:** 5×20 m (IW GRD), 6-day revisit (constellation).
- **Pipeline fit:** Optional validation / change detection; *not* v1 — SAR requires terrain-correction preprocessing that is out of scope.

### Landsat 8/9 (USGS)
- **Homepage:** https://www.usgs.gov/landsat-missions
- **Coverage:** Global, 16-day revisit, 1972–present (L8: 2013+, L9: 2021+)
- **Resolution:** 30 m multispectral, 15 m panchromatic
- **Auth:** Free ERS account for M2M API; **no auth** for STAC at `https://landsatlook.usgs.gov/stac-server` or for the `usgs-landsat` AWS requester-pays bucket (requester pays egress).
- **License:** Public domain.
- **Rate limits:** M2M has per-user download throttles; STAC search is unthrottled.
- **Python access:** `pystac-client` against landsatlook STAC; `usgs-m2m-api`/`landsatxplore` for M2M wrappers.
- **Pipeline fit:** Secondary to Sentinel-2 (lower resolution); useful only for longer-time-range context.

### NAIP (USGS / USDA)
- **Homepage:** https://naip-usdaonline.hub.arcgis.com
- **Coverage:** Continental US only, ~1–3 year revisit per state
- **Resolution:** 0.6–1 m, 4-band RGBN
- **Auth:** **None** via Planetary Computer STAC (requires SAS signing only for asset download — free subscription key). Also on AWS `s3://naip-source` (requester-pays).
- **License:** Public domain (US federal).
- **Rate limits:** None documented at STAC layer.
- **Python access:** Planetary Computer STAC is the cleanest route (`pystac-client` + `planetary-computer.sign()`).
- **Pipeline fit:** Texture draping on US AOIs — this is the highest-resolution free ortho Rook can ship derived renders from. First-class v1 target for US previews and validation.

### Maxar Open Data Program
- **Homepage:** https://www.maxar.com/open-data
- **Coverage:** Event-driven only — natural disasters (earthquakes, hurricanes, floods). NOT general-purpose coverage.
- **Resolution:** ~30–50 cm
- **Auth:** None (S3 public, AWS Open Data Registry + source.coop mirror).
- **License:** **CC BY-NC 4.0** — non-commercial only. Unusable for the common Rook use case (architect running a paid workflow).
- **Pipeline fit:** **Excluded from v1.** License conflicts with the typical Rook deployment. Document as "disaster-response mode only" for future.

### Planet (PlanetScope / RapidEye / SkySat)
- **Homepage:** https://www.planet.com
- **Coverage:** Global daily (PlanetScope, 3 m); very-high-res on-demand (SkySat, 50 cm).
- **Auth:** API key.
- **License:** Commercial unless user is in the Education & Research program (cap ~3,000 km²/month, 2–4 week approval, academic-only, non-commercial outputs).
- **Rate limits:** Tier-dependent.
- **Python access:** `planet` official SDK (v2, async-friendly).
- **Pipeline fit:** BYOK opportunistic — if a user already has a Planet key, offer it as an alternative high-res source. Not a default.

### Mapbox Static Images API
- **Homepage:** https://docs.mapbox.com/api/maps/static-images/
- **Coverage:** Global basemap + satellite composite (Mapbox blends Maxar, Airbus, DigitalGlobe under commercial license to their customers — ToS permits downstream use).
- **Resolution:** Up to ~15 cm in some metros; typically 50 cm–2 m global.
- **Auth:** Access token (public `pk.*` token is fine for static endpoint).
- **License:** Mapbox ToS — attribution required; caching restrictions apply (images must not be stored >30 days without customer having rights).
- **Rate limits:** 50,000 free map loads/month for the Standard map style on the Static Images API (exact SKU rules have shifted several times — check pricing page before shipping).
- **Python access:** Plain HTTP (no SDK needed); construct the URL with bbox + zoom.
- **Pipeline fit:** **v1 preview/thumbnail provider.** Fast, global, one-HTTP-call. Ideal for the AOI preview thumbnail shown in the Rook panel before the user commits to extraction.

### Google Static Maps
- **Homepage:** https://developers.google.com/maps/documentation/maps-static
- **Auth:** API key + billing account required.
- **License:** Google Maps Platform ToS — cannot save images for offline use, cannot re-distribute, attribution required. Strict compared to Mapbox.
- **Rate limits / pricing:** Since March 2025, the pooled $200/month credit is gone. Static Maps (an "Essentials" SKU) gets **10,000 free events/month**, then $2/1,000. Per-SKU caps don't pool.
- **Python access:** `googlemaps` SDK.
- **Pipeline fit:** Excluded from v1 — the caching restriction is incompatible with Rook's artifact model (persisted previews in `%TEMP%/rook/`). Mapbox's license is friendlier.

### Airbus OneAtlas / Nearmap / aerial commercial
- Commercial, region-specific, no free tier.
- **Pipeline fit:** Opportunistic BYOK — document the key-plug-in pattern but do not wire in v1.

### National aerial programs (UK APGB/Bluesky, etc.)
- Mostly paid or institutional. Out of scope for v1.

## Meta-catalog gateways

### Microsoft Planetary Computer *(recommended anchor)*
- **Homepage:** https://planetarycomputer.microsoft.com
- **Datasets exposed:** Sentinel-1/2, Landsat C2 L1/L2, NAIP, Copernicus DEM (GLO-30 / GLO-90), MS Global Building Footprints, OSM Buildings, Dynamic World, USGS 3DEP LiDAR, and ~150 more collections.
- **Auth:** Free "subscription key" (`PC_SDK_SUBSCRIPTION_KEY`) for signed-URL generation on managed-storage assets. Public STAC search itself requires no auth.
- **STAC compliant:** **Yes** — reference STAC API v1.0.0 implementation, powered the canonical STAC tooling.
- **License:** Per-dataset (all core open datasets inherit their permissive upstream licenses). No Planetary-Computer-specific commercial restrictions on the data.
- **Rate limits:** *Formally undefined.* Microsoft's position: "STAC search endpoints do not have rate limiting per-se, but it is a shared resource; individual throughput is sensitive to overall load." 503/504s under pressure. SAS tokens last ~1 hour; re-sign as needed.
- **Python access:** `pystac-client` + `planetary-computer` + `stackstac` / `odc-stac` / `rioxarray`. This is the de-facto reference stack for the whole open-geospatial Python community.
- **Pipeline fit:** Backbone. One key, many datasets, STAC-native, permissive. No commercial gotcha.

### Google Earth Engine
- **Homepage:** https://earthengine.google.com
- **Datasets exposed:** Larger than Planetary Computer — Sentinel, Landsat, MODIS, Copernicus DEM, ALOS, Global Forest Change, Dynamic World, WorldCover, Open Buildings, etc.
- **Auth:** Google Cloud project + service account (or OAuth). Enrolled as **noncommercial** or **commercial**.
- **STAC compliant:** **Partially** — Google publishes a STAC catalog of all Earth Engine assets for discovery, but data access is through the EE client (`ee` Python) and its tile server, not direct STAC asset HREFs.
- **License:** Non-trivial. **From 27 April 2026**, all noncommercial projects must select a quota tier or fall back to the "Community Tier" default free quota (monthly EECU-hours). Not-for-profit and academic orgs retain free noncommercial access. **A licensed architect using Rook for paid client work is commercial** and must carry an active paid Earth Engine plan (platform fee + usage-based EECU + storage).
- **Rate limits:** EECU compute quota (tier-dependent), concurrent-request limits, and daily batch-export ceilings.
- **Python access:** `earthengine-api` (`ee`), tightly coupled to Google's servers — no "fetch a GeoTIFF and work locally" idiom; exports are async jobs to Drive/GCS or synchronous `getDownloadURL` for small regions.
- **Pipeline fit:** Powerful for analysis (masking, compositing, time-series) but the commercial licensing footprint makes it a poor default. Wire it up as BYOK *alternative* for users who have opted in to an EE plan; do not make it the v1 anchor.

### AWS Open Data Registry
- **Homepage:** https://registry.opendata.aws
- **Datasets exposed:** Overlapping superset of Planetary Computer — Landsat, Sentinel, NAIP, Maxar Open Data, Copernicus DEM, OSM dumps, etc.
- **Auth:** None for public buckets; IAM credentials for requester-pays buckets (Landsat C2, NAIP-source).
- **STAC compliant:** Per-dataset. Element 84's **Earth Search** (https://earth-search.aws.element84.com/v1) is the de-facto public STAC front door for the AWS-hosted Sentinel-2 COGs and Landsat data.
- **License:** Per-dataset.
- **Rate limits:** S3 egress caps; requester-pays is user-funded.
- **Pipeline fit:** **Failover.** If Planetary Computer is down for Sentinel-2 or NAIP, Earth Search + direct S3 is the mirror. Wire the client to switch endpoints on PC 503.

### STAC (the spec)
- **Homepage:** https://stacspec.org
- Not a provider — a metadata convention. Supported by Planetary Computer, Earth Search (AWS), USGS LandsatLook, Copernicus Dataspace (partial), Radiant MLHub, and most modern catalogs.
- **Python libs:** `pystac` (objects), `pystac-client` (API queries), `stackstac` (lazy xarray from STAC items), `odc-stac` (alternative loader).
- **Pipeline fit:** This is the abstraction v1 codes against. All provider adapters should return STAC Items.

### OpenTopography
- LIDAR-focused. See terrain dossier for depth. Exposes a REST API + STAC mirror; no imagery relevance here.

### Radiant MLHub
- Training-label catalog (ML datasets, many STAC-labeled). Not v1 — the pipeline needs imagery, not ML corpora.

### Descartes Labs / SkyWatch EarthCache
- Commercial aggregators (Descartes is enterprise-priced; SkyWatch is pay-as-you-go with a free developer tier). Interesting future BYOK targets but no free-tier imagery path that beats Planetary Computer. Excluded from v1.

## Recommended BYOK matrix for v1

- **Anchor catalog:** **Microsoft Planetary Computer.** Free subscription key, STAC-native, covers Sentinel-1/2, Landsat, NAIP, Copernicus DEM, MS Buildings, and Dynamic World in one auth boundary. No commercial-use gotchas for a paid-workflow user. The `pystac-client` + `planetary-computer.sign()` pattern is <20 lines of Python.
- **Imagery providers to wire up in v1:**
  1. **Planetary Computer** — Sentinel-2 (global), NAIP (US), Landsat (fallback).
  2. **Mapbox Static Images** — cheap global preview thumbnail (user brings their own `pk.*` token; no key = skip preview, degrade gracefully).
  3. **Earth Search (AWS / Element 84)** — automatic failover for Sentinel-2 when PC returns 503/504.
- **Opportunistic adds (BYOK, documented but not default-wired):**
  - Google Earth Engine — for users who want compositing/time-series analysis and have an EE plan.
  - Planet — for users with an API key (commercial or Education tier).
  - Copernicus Dataspace direct — for users wanting raw SAFE archives rather than COG chips.
- **Excluded from v1:**
  - Maxar Open Data (CC-BY-NC bars commercial workflows).
  - Google Static Maps (ToS bars caching, pricing less friendly than Mapbox).
  - Airbus OneAtlas, Nearmap, Descartes, SkyWatch (commercial-only, no free path that beats the anchor).
  - Sentinel-1 SAR (preprocessing complexity, not needed for v1's preview/texture/validation triad).

## Open questions

1. **Mapbox Static SKU drift.** Mapbox's Static Images billing has changed three times since 2022. Before shipping v1, re-read their current pricing page and confirm the 50k-free-loads tier still applies to the style we use.
2. **Planetary Computer SAS token lifetime in long-running sessions.** Tokens expire in ~1 hour; if a user opens a Rook session and idles, the pre-signed asset URL dies. Decide whether to re-sign on every asset read (simple, correct) or cache with expiry check.
3. **Earth Engine tier auto-detection.** If we wire EE as BYOK, we cannot tell whether a user's key is noncommercial or commercial until a request fails. Do we ask them at setup, or let EE error messages drive it?
4. **NAIP attribution surface.** When Rook drapes NAIP on an extrusion and the user exports that texture in a rendered image, where does the "USDA / NAIP" attribution go? Bake into a sidecar JSON, overlay on export, or punt to user responsibility?
5. **Global coverage gap for 60 cm imagery.** Outside the US, nothing free beats Sentinel-2's 10 m. Architects in EU/Asia will hit this. Document the gap; note which commercial BYOK options (Airbus, Planet SkySat on-demand) patch it.
6. **Caching policy.** Mapbox ToS limits offline retention; Planetary Computer SAS URLs expire. Rook's artifact model wants to cache. The policy needs a dossier of its own or at least a cross-reference in the pipeline plan.

---

*Cross-references:* Terrain rasters (Copernicus DEM, USGS 3DEP, OpenTopography) covered in the terrain dossier. Building footprints (MS Global Buildings, Overture, OSM) covered in the footprints dossier. Both are reachable through Planetary Computer, which is why anchoring there compounds.
