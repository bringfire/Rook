# GIS BYOK — Building Footprints Dossier

**Part of:** [2026-04-24-gis-byok-pipeline-research.md](2026-04-24-gis-byok-pipeline-research.md)
**Status:** research (2026-04-24)

## Summary

For a global BYOK footprint pipeline, the minimal, copyleft-safe default is a three-way stack: **Overture Maps (buildings theme)** as the primary conflated global layer, **OpenStreetMap (via Overpass/osmnx)** as the live-edited fallback, and **Microsoft GlobalMLBuildingFootprints** for ML-derived coverage where Overture lags. Everything else — Google Open Buildings, EUBUCCO, 3DBAG, USA Structures, PLATEAU — is an opportunistic regional upgrade, not a substitute. Paid APIs (Mapbox, Esri) are BYOK niceties, not core providers, because their licenses are hostile to redistributing derived `.3dm`.

## Sources

### OpenStreetMap (via Overpass API / osmnx)
- **Homepage:** https://www.openstreetmap.org, https://overpass-turbo.eu
- **Coverage:** Global, crowd-sourced, wildly uneven. Western Europe near-complete; dense urban US, JP, AU good; rural Global South poor.
- **Vintage / update cadence:** Live; planet replicated minutely. Any single footprint is as recent as its last edit.
- **Attributes:** `building=*` (use class), `building:levels`, `height`, `name`, `addr:*`, `roof:shape`. Height is a string (`"12 m"`, `"12"`, `"39'"`) — Overture's parser is the reference implementation.
- **Auth:** None for Overpass; osmnx is a thin wrapper.
- **License:** ODbL 1.0 (share-alike). Derived `.3dm` is a Produced Work — attribution required, share-alike applies to the *database*, not to individual rendered outputs, but users redistributing the footprints in a shareable Rhino file are creating a Derivative Database.
- **Rate limits / quotas:** Public Overpass: ~10k req/day, ~1 GB/day, 180 s default timeout, 512 MiB memory. HTTP 429 on abuse. Self-host or use Kumi/Private.coffee mirrors for heavier loads.
- **Python access:** `osmnx` — `ox.features_from_point((lat, lon), tags={"building": True}, dist=500)`. Returns GeoDataFrame; filter to Polygon/MultiPolygon.
- **Pipeline fit:** Default for small radii (<2 km). Best-attributed for building use/name/address. Weakest on height — most records lack it.

### Overture Maps Foundation — Buildings theme
- **Homepage:** https://overturemaps.org, https://docs.overturemaps.org/guides/buildings/
- **Coverage:** Global. ~2.3 B footprints conflated from OSM (priority), Microsoft, Google, Esri Community Maps, and national open datasets. Monthly releases.
- **Vintage / update cadence:** Monthly GA releases (e.g. 2026-04-15, 2026-03-18, 2026-01-21). Latest release auto-targeted by STAC catalog.
- **Attributes:** `height` (meters, parsed/harmonized), `min_height`, `roof_height`, `num_floors`, `num_floors_underground`, `names` (multi-language), `class`, `subtype`, `sources[]` (per-property provenance with JSON Pointer). Fill rates vary sharply by region — no published completeness stat; empirically height is sparse outside Europe/US/JP.
- **Auth:** None.
- **License:** ODbL 1.0 for buildings theme (inherits from OSM). CDLA-Permissive-2.0 for themes without OSM input. Buildings *require* share-alike; attribution to Overture + OSM.
- **Rate limits / quotas:** None on the S3/Azure hosted Parquet. S3 egress costs fall on AWS, not user.
- **Python access:** `pip install overturemaps` then `overturemaps download --bbox=minx,miny,maxx,maxy -f geoparquet --type=building -o out.parquet`. Or read directly: `gpd.read_parquet` over an S3 URL with pyarrow filter pushdown.
- **Pipeline fit:** **Primary provider.** Conflated > OSM alone. Monthly cadence is fine for architecture use. Sole source that gives you provenance per-attribute.

### Microsoft GlobalMLBuildingFootprints
- **Homepage:** https://github.com/microsoft/GlobalMLBuildingFootprints, https://planetarycomputer.microsoft.com/dataset/ms-buildings
- **Coverage:** Global. ~1.4 B footprints from Bing imagery (Maxar, Airbus, IGN France) 2014–2024. Strong in US, EU, AU, much of Global South; gaps where imagery was older or cloudy. Feb-2025 update added 18 M footprints + 4.2 M heights (concentrated TR, GR, FR).
- **Vintage / update cadence:** Ad-hoc quarterly-ish. January 2026 added 3.5 M more. No set schedule.
- **Attributes:** Footprint polygon + quality/confidence. `height` available for subsets of EU/US/TR/GR only (~174 M total have heights — this is the bottleneck). No name, no use, no address.
- **Auth:** None for raw GitHub/Azure tiles. Planetary Computer STAC API requires a free Azure account for signed URLs on some collections; `ms-buildings` is currently public-read.
- **License:** ODbL 1.0 (changed from ODC-BY in 2022 to align with OSM import).
- **Rate limits / quotas:** None published. Files are quadkey-partitioned GeoJSON or Parquet on Azure Blob Storage.
- **Python access:** Planetary Computer route is cleanest — `pystac_client` + `planetary_computer.sign_item` + `gpd.read_parquet`. Collection is `ms-buildings`, partitioned by RegionName + quadkey. Raw GitHub route requires quadkey lookup + per-country GeoJSON download.
- **Pipeline fit:** Best for ML-coverage fallback when OSM/Overture thin. Heights only useful in EU/US — elsewhere you still need LIDAR/DSM.

### Google Open Buildings (v3 polygons + 2.5D Temporal)
- **Homepage:** https://sites.research.google/gr/open-buildings/
- **Coverage:** Regional, not global. v3 covers Africa, South Asia, Southeast Asia, Latin America & Caribbean — 58 M km² inference area, ~1.8 B detections. **No coverage of US, EU, Canada, AU, JP, CN.** Explicitly built to fill the Global South gap.
- **Vintage / update cadence:** v3 imagery c. May 2023. Temporal 2.5D adds annual height snapshots 2016–2023.
- **Attributes:** Polygon, confidence score, area. 2.5D Temporal variant adds annual building presence + height raster.
- **Auth:** None for direct CSV/Parquet on Google Cloud Storage. Earth Engine requires free account.
- **License:** Dual — choose CC-BY-4.0 or ODbL v1.0 per your downstream license needs. Attribution required either way.
- **Rate limits / quotas:** None on GCS tiles. EE has per-user quotas.
- **Python access:** `earthengine-api` for EE route. For raw: `gpd.read_file` on S3-mirror (Source Cooperative) or direct GCS CSV/Parquet per s2 cell. `open-buildings` package (gishub) wraps the download workflow.
- **Pipeline fit:** **Essential for Global South.** Where Overture/Microsoft are thin, Google fills in. No heights in the polygon dataset alone — pair with 2.5D Temporal for heights.

### VIDA Google–Microsoft–OSM Combined
- **Homepage:** https://source.coop/vida/google-microsoft-osm-open-buildings
- **Coverage:** Global. 2.7 B footprints across 200 country partitions (May 2025 update). Each feature tagged with source (Google / Microsoft / OSM).
- **Vintage / update cadence:** Irregular; refreshed when upstream sources update. Not a Foundation-backed release — VIDA engineering publishes it.
- **Attributes:** Polygon + source tag + upstream attrs (height where present via MS). Lossy merge vs. Overture's richer provenance.
- **Auth:** Source Cooperative account (free) for AWS credentials, or public HTTPS mirror.
- **License:** Inherits ODbL from upstream.
- **Python access:** GeoParquet / FlatGeobuf / PMTiles. `gpd.read_parquet` over S3 with partition filtering by country ADM0.
- **Pipeline fit:** **Opportunistic alternative to Overture** if you want one file per country rather than per tile. Overture is generally preferable because of schema and conflation quality, but VIDA's per-country partitioning is convenient for country-scoped pipelines.

### Esri / ArcGIS Living Atlas — World Buildings
- **Homepage:** https://livingatlas.arcgis.com
- **Coverage:** Global aggregation of authoritative sources (national cadastre layers + Overture + community contributions). Coverage depth depends on Esri's per-country agreements.
- **Auth:** ArcGIS Online account. Premium/Subscriber content often gated behind paid ArcGIS user type (Professional / Professional Plus); may consume credits per query.
- **License:** **Mixed and restrictive.** Individual layers have their own terms. Most are not redistributable — Esri licenses the use, not the data.
- **Python access:** `arcgis` SDK (`GIS.content.search`), or query the feature service REST endpoint.
- **Pipeline fit:** **Exclude from v1.** License hostile to distributing `.3dm` outputs. Include only as a BYOK-for-enterprise plugin later, with explicit warnings.

### Mapbox Streets / Buildings layer
- **Homepage:** https://docs.mapbox.com/api/maps/vector-tiles/
- **Coverage:** Global, derived primarily from OSM with proprietary additions.
- **Auth:** Required API key.
- **License:** Mapbox Terms of Service. Derived geometry may NOT be extracted and redistributed. You can render, not re-export.
- **Rate limits / quotas:** Tile-request based; free tier exists.
- **Python access:** Vector tile decoders (`mapbox-vector-tile`, `vt2geojson`) — but extracting geometry for redistribution violates ToS.
- **Pipeline fit:** **Exclude.** Wrong license for a pipeline that produces shareable `.3dm`. Users who want Mapbox rendering can pair it with Rook separately; it's not a footprint provider.

### USA Structures (FEMA / ORNL / DHS S&T)
- **Homepage:** https://gis-fema.hub.arcgis.com/pages/usa-structures
- **Coverage:** US + territories. 125 M+ structures >450 sq ft, CNN-extracted from Maxar + NAIP imagery.
- **Vintage / update cadence:** Periodic; backed by FEMA disaster-response need.
- **Attributes:** Footprint + height (OCCUPIED), occupancy class (RES/COM/IND/etc.), address, county FIPS.
- **Auth:** None for public download.
- **License:** Public domain (US government work).
- **Python access:** Shapefile/GDB download from FEMA Geoplatform or Figshare. No official Python client; `geopandas.read_file` handles it.
- **Pipeline fit:** **Best-in-class US layer.** Beats Microsoft/Overture on US attribution because of occupancy + height. Use when AOI is US.

### Ordnance Survey OpenMap Local (UK)
- **Homepage:** https://osdatahub.os.uk/downloads/open/OpenMapLocal
- **Coverage:** England, Wales, Scotland. Derived from authoritative OS topographic surveys.
- **Vintage / update cadence:** Biannual.
- **Attributes:** Building + "important building" classification. No height in OpenMap Local — you'd need paid OS MasterMap or the `OS Zoomstack` complement. Heights come from the LIDAR nDSM route instead (which the original Streamlit app does).
- **Auth:** Free OS Data Hub account for API; direct download link-only, no auth.
- **License:** Open Government Licence v3 (OSM-compatible, attribution required).
- **Python access:** Zipped Shapefile/GeoPackage download → `gpd.read_file`. No native Python client; the `OS Data Hub` has a REST API keyed by free API key.
- **Pipeline fit:** Authoritative UK upgrade over OSM. Use when AOI is UK and you want cadastre-grade geometry.

### 3DBAG (Netherlands, TU Delft + Geonovum)
- **Homepage:** https://3dbag.nl, https://docs.3dbag.nl
- **Coverage:** Netherlands only. ~10 M buildings. LoD1.2 / LoD1.3 / LoD2.2 already extruded.
- **Vintage / update cadence:** Continuous; full refresh ~quarterly.
- **Attributes:** Footprint + validated height + roof type + BAG ID + build year. Already 3D.
- **Auth:** None.
- **License:** CC-BY 4.0 (attribution to 3DBAG + Kadaster + AHN).
- **Python access:** CityJSON, OBJ, GeoPackage per-tile downloads. `cjio` for CityJSON; `gpd.read_file` for GPKG. OGC API Features endpoint.
- **Pipeline fit:** **If AOI is NL, skip the DSM pipeline entirely** — 3DBAG already ships the LoD1/LoD2 model. Highest-quality single-country layer in the world.

### PLATEAU (Japan, MLIT)
- **Homepage:** https://www.mlit.go.jp/plateau/en/
- **Coverage:** ~250 Japanese cities with CityGML LoD1/LoD2 (some LoD3). Growing annually.
- **Vintage / update cadence:** Annual FY releases.
- **Attributes:** CityGML — footprint + height + use + LOD + address. Rich semantic model.
- **Auth:** None.
- **License:** CC-BY 4.0.
- **Python access:** CityGML is the native format — `citygml4j` (Java), or convert via `cjio` / FME / `citygml-tools`. Python support is thinner than for GeoPackage. **Python story is painful** — users typically convert once via cjio and cache as CityJSON or GeoPackage.
- **Pipeline fit:** Japan-only upgrade; already 3D so the DSM stage is skippable. Friction in Python makes it an opt-in provider, not a default.

### ALKIS Hausumringe (Germany, per-Land)
- **Homepage:** https://gdk.gdi-de.org (federated state portals)
- **Coverage:** Germany, but **fragmented by Bundesland**. NRW, Berlin, Brandenburg, Hessen, Sachsen, Baden-Württemberg, Thüringen publish openly. Bavaria historically paid-only (has been opening up).
- **Vintage / update cadence:** Varies by state; typically monthly or quarterly.
- **Attributes:** Cadastral footprint. Heights only in LoD1/LoD2 datasets from separate Landesvermessung products (e.g. LoD2-DE, 3D-Gebäudemodell).
- **Auth:** Varies — most states: none.
- **License:** Datenlizenz Deutschland – Zero 2.0 or BY 2.0 (OSM-compatible), per state.
- **Python access:** Shapefile/GML per state → `gpd.read_file`. `v.alkis.buildings.import` (GRASS) automates NRW/BE/BB/HE/SN downloads. **No unified German endpoint** — user or pipeline must know the state. Friction worth flagging.
- **Pipeline fit:** DE regional upgrade but fragmentation makes it awkward for a global-provider registry. Defer to Overture for DE unless user asks for cadastral-grade.

### EUBUCCO v0.1 (research dataset)
- **Homepage:** https://eubucco.com
- **Coverage:** EU-27 + NO, CH, UK. 378 M buildings aggregated from 50+ national open datasets.
- **Vintage / update cadence:** v0.1 (2022); v0.2 announced with 322 M (different boundary choices). Academic cadence — not continuously updated.
- **Attributes:** Footprint, height (where upstream had it), build year, use type, national source tag. ~45% have height; coverage is best in DE/NL/FR/ES.
- **Auth:** None.
- **License:** Mostly ODbL. Two upstream datasets have different licenses and are filename-tagged. Check per-file before redistributing.
- **Python access:** Zenodo download → GeoPackage/Parquet → `geopandas`. No live API.
- **Pipeline fit:** Academic baseline for EU comparative work. For a live pipeline, Overture already subsumes most of it. Skip for v1 unless doing research-grade EU stock analysis.

### GlobalBuildingAtlas (TUM, 2025)
- **Homepage:** https://github.com/zhu-xlab/GlobalBuildingAtlas, https://essd.copernicus.org/articles/17/6647/2025/
- **Coverage:** Global. 2.75 B building models; 97% have LoD1 3D. Imagery c. 2019.
- **Attributes:** Footprint + height (3 m raster resolution) + LoD1 extrusion as CityJSON.
- **Auth:** mediaTUM download; WFS endpoint also published.
- **License:** **Split** — GBA.ODbLPolygon subset is ODbL; GBA.Polygon + GBA.LoD1 + GBA.Height are CC-BY-NC 4.0. **Non-commercial clause excludes most of this dataset from a redistributable plugin.** The ODbL subset is useful; the NC subset is not for Rook's use case.
- **Python access:** mediaTUM tiles → `gpd.read_file` / `cjio`. WFS via OGR.
- **Pipeline fit:** Opportunistic height layer *only* the ODbL subset. The NC clause is a hard stop for anything else. Flag clearly in provider docs.

### OpenBuildingMap (OBM)
- **Homepage:** https://openbuildingmap.org
- **Coverage:** Global semantic-enriched OSM buildings (adds predicted use/height via ML).
- **License:** ODbL.
- **Python access:** Postgres/PBF dumps; not an ergonomic client.
- **Pipeline fit:** Research-grade. Skip for v1.

## Coverage gap map

| Region | Best free layer | Second | Height available? |
|---|---|---|---|
| US | USA Structures | Overture | Yes (USA Structures) |
| UK | OS OpenMap Local | Overture + OSM | No — needs LIDAR nDSM |
| NL | 3DBAG (already 3D) | — | Yes, LoD1/LoD2 |
| DE | ALKIS per-state OR Overture | OSM | Height via LoD2-DE (state-level) |
| FR/ES/IT | Overture | OSM + EUBUCCO | Partial (MS heights in FR) |
| Nordics | Overture | OSM + national cadastres | Patchy |
| JP | PLATEAU | Overture | Yes (PLATEAU) |
| AU/NZ | Overture + MS | OSM | No |
| Africa | Google Open Buildings | Overture | Only via Google 2.5D Temporal |
| S/SE Asia | Google Open Buildings | Overture | Only via Google 2.5D Temporal |
| LatAm/Caribbean | Google Open Buildings | Overture | Only via Google 2.5D Temporal |
| China | Overture (OSM-derived, thin) | MS | No |
| Middle East | Overture | MS | Partial (MS heights in TR) |

**Hard gaps:** Global polar/remote regions and parts of Central Asia still have poor footprint data in all sources. No provider solves this — it's an imagery-availability problem upstream.

## Recommended BYOK matrix for v1

**Core (ship in v1):**
1. **Overture Maps** — default provider. Best schema, best conflation, no key.
2. **OpenStreetMap via Overpass/osmnx** — live fallback, small-AOI default, no key.
3. **Microsoft GlobalMLBuildingFootprints** — ML fallback for regions where 1+2 thin. No key.
4. **Google Open Buildings (v3 + 2.5D Temporal)** — region-gated auto-switch for Africa/S Asia/SE Asia/LatAm. No key.

**Opportunistic regional upgraders (ship if the country matches AOI, otherwise skip):**
- **USA Structures** — auto-prefer for US AOI.
- **3DBAG** — auto-prefer for NL AOI (and skip DSM stage).
- **OS OpenMap Local** — auto-prefer for UK AOI.
- **PLATEAU** — opt-in for JP AOI (Python friction).

**Deferred / excluded:**
- **Esri Living Atlas** — license hostile to `.3dm` redistribution.
- **Mapbox** — ToS forbids geometry extraction.
- **EUBUCCO** — subsumed by Overture for live use; keep for research mode.
- **GlobalBuildingAtlas (non-ODbL subset)** — CC-BY-NC kills it for redistributable outputs.
- **ALKIS per-Land** — fragmentation too high for a v1 abstraction; revisit once Germany consolidates.

This mirrors the LiteLLM pattern: one default (Overture), one live-edited fallback (OSM), one ML fallback (MS), one regional router (Google), and country-preferred upgraders when AOI hits.

## Open questions

- **Height-fill rate per region for Overture** — no published stat. Need a spike: pull 10 random urban bboxes per continent and measure `height` null rate. Result determines whether Microsoft heights are "often needed" or "rarely needed" backup.
- **Overture ODbL share-alike scope on `.3dm` outputs** — is a single user's exported `.3dm` a "Produced Work" (attribution only) or a "Derivative Database" (share-alike)? Opinion varies. Needs legal review before shipping a "publish to GitHub" button.
- **Can the pipeline auto-switch provider based on AOI centroid?** A routing table keyed on country/region is straightforward but creates user-visible inconsistency in output quality. Consider showing "Used: Overture (3,412 buildings) + Microsoft (heights for 41%)" as telemetry.
- **Do we need a paid-tier provider at all?** If Overture + Google + Microsoft cover 95% of architecturally-interesting AOIs at good quality, Esri/Mapbox may be permanent exclusions rather than deferred.
- **Provenance carry-through** — Overture emits per-property sources. Should we preserve these as UserText on each `.3dm` instance? Argues yes; storage cost is trivial and it unlocks attribution compliance.
