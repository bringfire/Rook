# GIS BYOK Pipeline — Research Brief

**Status:** research complete, synthesis drafted (2026-04-24)
**Owner:** aryan
**Trigger:** reverse-engineered `lidar2building.streamlit.app` outputs (central London AOI, 500 m buffer, BNG). Pipeline: lat/lon → AOI buffer → LIDAR DSM+DTM → nDSM → OSM footprints → zonal stats per footprint → extrude to `.3dm`. App is UK-only because it hardwires EA LIDAR + British National Grid.

## Goal

Define a BYOK contract for the geospatial pipeline so that, wherever a user has a key (or a free public source exists), Rook can produce the lidar2building-equivalent outputs (AOI, DTM, DSM/nDSM, building footprints with heights, extruded Rhino model) for any AOI globally — mirroring the LiteLLM pattern we use for LLM providers.

## Pipeline axes under research

1. **Building footprints** — OSM, Microsoft Global Buildings, Google Open Buildings, Overture, Mapbox, Esri
2. **Terrain (DTM) + Surface (DSM / nDSM)** — national LIDAR programmes (UK/US/EU/AU/NZ), global DEMs (SRTM, Copernicus GLO-30), meta-catalogs (OpenTopography, GEE, Planetary Computer), direct building-height datasets (MS, Overture, OSM tags) as DSM fallback
3. **Imagery + meta-catalogs** — Sentinel-2 / Landsat (free), Mapbox / Planet / Maxar (keyed), the major catalog gateways (GEE, Planetary Computer, AWS Open Data, STAC) that wrap many sources behind one auth
4. **Geocoding + reverse geocoding** — Nominatim (free), Mapbox / Google / Bing / HERE (keyed)

## Research dossiers

Each axis gets a standalone dossier:

- [2026-04-24-gis-byok-footprints.md](2026-04-24-gis-byok-footprints.md) — building footprints sources
- [2026-04-24-gis-byok-terrain-dsm.md](2026-04-24-gis-byok-terrain-dsm.md) — DTM, DSM, nDSM, building-height fallbacks
- [2026-04-24-gis-byok-imagery-catalogs.md](2026-04-24-gis-byok-imagery-catalogs.md) — imagery providers and meta-catalog gateways
- [2026-04-24-gis-byok-geocoding.md](2026-04-24-gis-byok-geocoding.md) — geocoding providers

## Dossier template

Each source entry captures:

- **Name** + homepage
- **Coverage** (global / national / regional) — with an explicit gap map when partial
- **Resolution / vintage** (for rasters and footprint datasets)
- **Auth model** — none / account / API key / OAuth / paid tier
- **License** — can derived `.3dm` be shared? redistribution terms for raw tiles?
- **Rate limits / quotas** — free-tier caps, paid tier shape
- **Python access** — canonical library (`rasterio`, `pystac-client`, `osmnx`, `geopandas`, `earthengine-api`, provider SDK)
- **Pipeline fit** — which pipeline stage(s) it serves, and any known quality caveats

Each dossier also ends with a **Recommended BYOK matrix** — which sources belong in a v1 provider registry, which are opportunistic adds, which are excluded and why.

## Load-bearing question for the terrain dossier

**Where does the DSM layer come from outside well-surveyed countries (UK/US/EU/AU)?** If the honest answer is "nowhere free at building-scale resolution," the pipeline needs a graceful-degradation path: fall back to Microsoft / Overture ML-derived building heights, skip zonal stats entirely. The terrain dossier must answer this explicitly.

## What this doc is NOT

- Not an implementation plan. That comes after the dossiers land and we pick the minimal v1 matrix.
- Not a quality benchmark. That needs a real AOI comparison, done after the catalog is chosen.
- Not a commitment to ship. Feeds the `rook_geo` / image-to-CAD / RookVision strategy discussion.

---

# Findings Synthesis

## Three cross-cutting findings

### 1. There is no free global DSM at building scale

This is the *central* architectural constraint. The UK/US/EU/AU/NZ/JP have national LIDAR DSM at 0.5–1 m. Everywhere else (all of Africa, most of Asia, LatAm, Middle East, Russia, interior Canada, Greenland, Antarctica) has **nothing free at ≤5 m**. Copernicus GLO-30 is global but at 30 m it resolves neighbourhoods, not roofs. TanDEM-X 12 m is not redistributable without an Airbus agreement.

**Consequence for the pipeline:** the DSM-minus-DTM computation that lidar2building hardwires cannot be the whole pipeline. The "building height source" must be an abstract `HeightProvider` with two implementations — `DSMMinusDTMProvider(dsm, dtm)` (LIDAR path) and `AttributeHeightProvider(features)` (direct height attribute path). The extruder consumes the provider; it does not care which path fed it. Outside the LIDAR archipelago, the graceful-degradation ladder is: Microsoft ML heights → Overture `height` → Google Open Buildings 2.5D (excellent for Global South) → GHS-BUILT-H 100 m last-resort.

### 2. Storage-license is the load-bearing BYOK contract constraint

Rook writes geocoded coordinates, imagery previews, and extruded geometry into filenames, `.3dm` User Text, and project artifacts. That is **caching/persistence** under every major provider's ToS, and the terms diverge sharply:

- **Google Geocoding:** 30-day cache cap — structurally incompatible with persistent `.3dm` projects. Excluded.
- **Mapbox:** Temporary (forbids storage) and Permanent ($5/1k, allows storage) are separate SKUs and must be separate registry entries. One entry conflates two licenses.
- **Google Earth Engine:** the 2026-04-27 noncommercial-tier change means paid-workflow users must use the commercial tier. GEE cannot be a default code path until licensing posture is clarified; BYOK ambiguous because the request uses user credentials but the application is Rook.
- **Maxar Open Data:** CC-BY-NC — bars any commercial architectural workflow from shipping derivatives. Excluded even though "free."

**Consequence for the pipeline:** every provider registry entry carries a `storage_allowed: true | false | paid_tier_only` flag and an attribution string. The pipeline refuses to persist when the active provider forbids it. This is the single highest-value abstraction to land before shipping.

### 3. Regional specials bypass parts of the pipeline

Three countries have datasets that make the DSM-plus-extrude flow redundant:

- **Netherlands:** 3DBAG already ships LoD1/LoD2 extruded geometry. The pipeline should detect NL AOIs and route to a "download-LoD2-and-import" path, skipping DSM fetch and zonal stats entirely.
- **United States:** USA Structures (FEMA/ORNL, public domain) has 125M+ footprints with occupancy class *and* height. Prefer it over Overture/MS for US AOIs.
- **Japan:** PLATEAU ships CityGML at LoD1/LoD2/LoD3 for covered cities. CityGML Python story is painful (flag: `citygml-tools`, `cjio`), but the data quality is a generational lead when it matches.

**Consequence for the pipeline:** the AOI centroid routes not just between providers, but between pipeline shapes. The abstraction has to support "skip this stage entirely" as a valid provider output.

## Recommended v1 BYOK provider matrix

| Axis | No-key default | Key-gated (recommend) | Opportunistic | Excluded from v1 |
|---|---|---|---|---|
| **Geocoding** | Nominatim (1 req/s, branded User-Agent) | LocationIQ, Geoapify, Mapbox Permanent | Esri, Geocode Earth, Photon (autocomplete) | Google, HERE, Azure, TomTom, Bing (retired), Mapbox Temporary |
| **Footprints** | Overture (default), OSM/Overpass (fallback), Microsoft Global Buildings, Google Open Buildings | — (all free) | USA Structures (US auto-route), 3DBAG (NL auto-route), OS OpenMap Local (UK), PLATEAU (JP opt-in) | Esri Living Atlas, Mapbox, EUBUCCO, GBA-NC subset, per-Land ALKIS |
| **DTM** | Copernicus GLO-30 via AWS (unsigned) | OpenTopography API key (higher quota), NASA Earthdata (NASADEM) | National 1 m DTMs plugged in per-AOI (EA, 3DEP, IGN, AHN4, LINZ, swisstopo) | Commercial DEMs (Nearmap, Maxar Precision3D, Hexagon, Vexcel) |
| **DSM / nDSM** | National LIDAR DSM where AOI hits (UK EA, 3DEP, AHN4, IGN LiDAR HD, LINZ, swissSURFACE3D) | Copernicus Dataspace (EEA-10 10 m Europe) | — | TanDEM-X 12 m (not redistributable) |
| **Height attributes (DSM fallback)** | Overture `height`, Microsoft ML heights, Google Open Buildings 2.5D, GHS-BUILT-H | GEE service account (Open Buildings 2.5D zonal stats) | — | Nearmap AI, commercial heights |
| **Imagery / meta-catalog** | Microsoft Planetary Computer (anchor — Sentinel-2, Landsat, NAIP, Copernicus DEM, MS Buildings via STAC), Earth Search on AWS (failover) | Mapbox Static (preview thumbnails, user's `pk.*`) | Planet (Education/Research), Copernicus Dataspace (raw SAFE), GEE (after licensing clarified) | Maxar Open Data (CC-BY-NC), Google Static Maps (ToS + caching), Airbus/Nearmap/Descartes/SkyWatch |

**Anchor decision:** Microsoft Planetary Computer is the single backbone. STAC-native, one free subscription key, no commercial gotcha on open datasets, and it transitively exposes Copernicus DEM, MS Buildings, Sentinel-2, and NAIP — collapsing three of the four axes into one auth boundary.

## The BYOK contract shape that falls out

Each provider in the registry is shaped like:

```python
{
    "id": "overture",
    "axis": "footprints",                  # footprints | dtm | dsm | heights | imagery | geocoding
    "auth": "none",                        # none | account | key | oauth
    "storage_allowed": True,               # true | false | paid_tier_only
    "attribution": "© Overture Maps Foundation (ODbL / CDLA-2.0)",
    "redistribution_policy": "odbl_share_alike",  # free_derivative | attribution_only | odbl_share_alike | nc_only | forbidden
    "python_adapter": "rook_geo.providers.overture:OvertureFootprints",
    "region_hints": ["global"],            # for AOI-based auto-routing
    "rate_limits": {...},
    "cost_model": {...},
}
```

Three behaviors follow:

1. The pipeline **refuses to persist to `.3dm` when `storage_allowed=False`**. Project-save throws a license-wall error with the fix ("switch to LocationIQ, Nominatim, or Mapbox Permanent").
2. AOI centroid + `region_hints` **auto-promotes regional specials** (3DBAG over Overture for NL; USA Structures over MS for US).
3. Attribution strings land as **Rhino document User Text** on save — one entry per provider used, plus query date.

## Open questions rolled up from the dossiers

**Contract / legal:**
- Overture ODbL share-alike — is a user's exported `.3dm` a "Produced Work" (attribution only) or "Derivative Database" (share-alike)? Legal review before any publish-to-GitHub flow.
- GEE commercial-tier posture for BYOK — user's credentials, our application. Google's definition is ambiguous. Needed before making GEE default.
- Copernicus DEM AWS bucket LICENSE — confirm the July 2025 CC-BY 4.0 migration applies to `s3://copernicus-dem-30m/` specifically; fetch at build time.

**Quality / coverage:**
- Overture `height` null rate per continent — spike: pull 10 random urban bboxes per region, measure. Drives whether MS heights are "often needed" or "rarely needed" fallback.
- Microsoft Buildings height-coverage inventory — no published country-by-country table. Needs empirical probing.
- Germany state LIDAR — is there a single open WMS/WCS, or do we need 16-way per-Land integration?
- Global 60-cm imagery gap — outside the US, nothing free beats Sentinel-2's 10 m. Document the gap; don't pretend to solve it.

**UX / engineering:**
- Autocomplete via Photon (ephemeral) vs storage-legal provider for final persistence — one-provider or two-provider geocoder?
- Mapbox Static SKU drift — pricing has changed 3× since 2022. Re-verify before shipping.
- Planetary Computer SAS token 1-hour expiry in long sessions — re-sign per read, or cache with expiry check.
- Attribution surfacing in the Rhino document — User Text is cleanest; confirm via `rhino_usertext_document_set`.

## Next steps (proposed, not committed)

1. **Empirical spike** — pick 4 AOIs (London, Rotterdam, Lagos, São Paulo), run each candidate provider by hand, compare. This is where "observe before theorizing" earns its keep. One week of work, one doc.
2. **Draft the `rook_geo` substrate** — adapter interface, provider registry, `HeightProvider` protocol, storage-flag gate. Mirror the Vision three-layer doctrine (domain / programmatic / human).
3. **BYOK UI shape** — how do keys get in? `.env`, settings panel, per-session? Aligns with existing LiteLLM convention.
4. **Decide on LoD fidelity** — lidar2building ships flat-roof LoD1. Is that enough, or do we want to pull 3DBAG-style LoD2 (gabled roofs) when the source permits?

Each of these is its own follow-up doc.
