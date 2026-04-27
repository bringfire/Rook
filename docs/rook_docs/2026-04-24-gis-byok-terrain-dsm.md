#  GIS BYOK — Terrain, DSM, Building Heights Dossier

**Part of:** [2026-04-24-gis-byok-pipeline-research.md](2026-04-24-gis-byok-pipeline-research.md)
**Status:** research (2026-04-24)

## Summary

For a lat/lon-driven pipeline that extrudes buildings to a `.3dm`, **DTM is effectively solved globally** (Copernicus GLO-30, free, CC-BY, trivial Python access). **DSM at building-useful resolution (≤5 m) is not a solved problem outside ~20 countries** — the realistic path is (a) use national LIDAR where it exists, (b) otherwise fall back to *direct building-height attributes* (Microsoft, Overture, Google Open Buildings 2.5D, GHS-BUILT-H) and skip the DSM minus DTM math entirely. Treat "nDSM via LIDAR" as a feature-flagged premium path, not the pipeline default.

## LOAD-BEARING QUESTION (answer first)

**Where does the DSM layer come from outside the UK / US / EU / AU / JP?**

Short answer: *nowhere free at ≤5 m resolution*. Copernicus GLO-30 is labelled a DSM and is truly global (~149 M km²), but at 30 m it's too coarse to resolve individual buildings — it gives you neighbourhood-scale canopy/built height, not per-footprint roof elevations. TanDEM-X 12 m exists but is not open for general redistribution.

The realistic graceful-degradation ladder:

1. **National LIDAR DSM** (UK EA, USGS 3DEP, NL AHN4, FR IGN LiDAR HD, NZ LINZ, CH swisstopo, parts of DE/AT/Nordics) — when lat/lon is in-coverage, use this. 0.5–1 m, often includes first-return DSM + DTM.
2. **Direct building-height attributes** (Microsoft ML heights, Overture `height`, Google Open Buildings 2.5D, GHS-BUILT-H) — when LIDAR coverage is absent. Skip nDSM math; join height attribute onto the footprint directly.
3. **Copernicus GLO-30 as *DTM*** (yes, it's technically a DSM, but used as bare-earth base it's fine for extrusion-from-ground in flat-enough terrain — vertical RMSE ~4 m).
4. **Commercial keyed sources** (Nearmap, Maxar/Vexcel via Precisely, Hexagon) — if the user has a key. Out of scope for v1 free tier.

There is **no free global DSM at building scale**. This is the central constraint. Design the pipeline so the "height input" is an abstract provider, not a hardwired DSM−DTM computation.

---

## Sources — DTM (bare earth)

### Copernicus GLO-30 (the global baseline — use this)
- **Homepage:** https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM
- **Coverage:** Global ~149 M km². Small tile gaps (a few sovereign holdouts in GLO-30 Public). High-latitude coverage solid (derived from TanDEM-X).
- **Resolution:** 30 m (GLO-30), 90 m (GLO-90). EEA-10 at 10 m for Europe only.
- **Vintage:** 2011–2015 acquisition, last refresh 2023_1 (via OpenTopography mirror Jul 2024).
- **Auth:** None for AWS S3 / OpenTopography mirror. Copernicus Data Space has free registration.
- **License:** CC-BY 4.0 (as of July 2025 migration from the old Copernicus-products licence). **Redistribution of derivatives in a `.3dm` file is allowed with attribution.**
- **Rate limits:** AWS open bucket is unmetered. OpenTopography API: 500 calls / 24 h, max 4.05 M km² per COP90 request.
- **Python access:** `rasterio.open("s3://copernicus-dem-30m/...")` with no-sign-request, or `bmi-topography`, or `planetary-computer` STAC client. Cloud-Optimized GeoTIFF — streams windowed reads.
- **Pipeline fit:** Primary DTM everywhere. **Nominally a DSM**, but the SAR-derived "surface" at 30 m is closer to bare earth in non-forested areas than a LIDAR DSM; treat as DTM for extrusion purposes in graceful-degradation mode.

### NASADEM (SRTM successor)
- **Homepage:** https://lpdaac.usgs.gov/products/nasadem_hgtv001/
- **Coverage:** Global 60° N–56° S (SRTM footprint). **No polar coverage.**
- **Resolution:** 30 m (1 arc-second).
- **Vintage:** 2000 acquisition, 2020 reprocessing.
- **Auth:** NASA Earthdata login (free).
- **License:** Public domain.
- **Rate limits:** Via OpenTopography, same API budget.
- **Python access:** `earthaccess`, `rasterio`, or OpenTopography bulk.
- **Pipeline fit:** DTM fallback if GLO-30 tile is missing. Slightly worse vertical accuracy than GLO-30 (MAE 3.1 m vs GLO-30 ~2 m).

### ALOS AW3D30
- **Homepage:** https://www.eorc.jaxa.jp/ALOS/en/dataset/aw3d30/aw3d30_e.htm
- **Coverage:** Global-ish, but has gaps (notably some tropical / high-relief tiles).
- **Resolution:** 30 m.
- **Vintage:** 2006–2011, v3 updated 2021.
- **Auth:** JAXA free registration.
- **License:** Free for any use with attribution.
- **Python access:** OpenTopography mirror via `boto3` or `bmi-topography`.
- **Pipeline fit:** Best-accuracy 30 m open DSM (MAE ~2.5 m per Uuemaa et al. 2020). Redundant with GLO-30; keep as last-resort fallback.

### ASTER GDEM v3
- **Coverage:** 83° N–83° S (beats SRTM at high latitudes).
- **Resolution:** 30 m. Vertical MAE ~6 m — worst of the global set.
- **Pipeline fit:** Only useful above 60° N where SRTM/NASADEM don't reach and GLO-30 has gaps.

### USGS 3DEP (US — DTM flavour)
- **Homepage:** https://www.usgs.gov/3d-elevation-program
- **Coverage:** CONUS + Alaska + Hawaii + territories. Full 1-m coverage not yet complete (expanding as QL2+ LIDAR is acquired).
- **Resolution:** 1 m (where LIDAR exists), 3 m, 10 m, 30 m.
- **Auth:** None.
- **License:** Public domain.
- **Python access:** `py3dep`, Planetary Computer STAC, direct COG URLs.
- **Pipeline fit:** US DTM primary. Supersedes GLO-30 in-country.

### UK Environment Agency LIDAR Composite (UK — DTM flavour)
- **Homepage:** https://environment.data.gov.uk/dataset/13787b9a-26a4-4775-8523-806d13af58fc
- **Coverage:** ~99% of England; Scotland/Wales/NI via separate programmes.
- **Resolution:** 1 m composite, 50 cm time-stamped tiles.
- **Vintage:** 2000–2022.
- **License:** Open Government Licence. Redistribution OK with attribution.
- **Python access:** Defra Data Services WFS/WCS; GeoTIFF tiles in 5 km OS grid.
- **Pipeline fit:** UK DTM + DSM primary (this is what `lidar2building.streamlit.app` uses).

---

## Sources — DSM / nDSM

### UK EA LIDAR (DSM — first return)
Same source as above. Ships both DTM and DSM 1-m bands. nDSM computable directly. This is the gold standard the Streamlit app is built on.

### USGS 3DEP DSM
- 3DEP also produces DSM products (`3dep-lidar-dsm` STAC collection on Planetary Computer) at 1 m where LIDAR is QL2+. Coverage is patchier than DTM. Python: `pystac-client` against Planetary Computer, sign with `planetary-computer`.

### Netherlands AHN4
- **Homepage:** https://www.ahn.nl/
- **Coverage:** Full national, CC-0.
- **Resolution:** 0.5 m DSM + DTM.
- **Vintage:** 2020–2022.
- **Python:** WCS at `https://service.pdok.nl/rws/ahn/wcs/`, layers `dsm_05m` / `dtm_05m`, CRS EPSG:28992 (RD New).
- **Pipeline fit:** NL primary. Use directly.

### France IGN LiDAR HD
- **Homepage:** https://geoservices.ign.fr/lidarhd
- **Coverage:** Nationwide coverage achieved 2023.
- **Resolution:** 10 points/m² point cloud → 0.5 m / 1 m rasters.
- **License:** Open (etalab 2.0 / ODbL equivalent).
- **Python:** Tile download; point clouds in LAZ. Needs PDAL for rasterisation.
- **Pipeline fit:** FR primary.

### Switzerland swissALTI3D / swissSURFACE3D
- **Homepage:** https://www.swisstopo.admin.ch/en/geodata/height/surface3d.html
- **Resolution:** 0.5 m DSM (swissSURFACE3D), 0.5 / 2 m DTM.
- **License:** Free since 2021.
- **Pipeline fit:** CH primary.

### Germany (fragmented — Länder level)
- No federal open DSM. State-by-state: Thuringia, NRW, Berlin, Hamburg, Brandenburg, Saxony have open LIDAR; Bavaria is paywalled; others vary. Expect **significant integration effort**.
- Aggregator: Sonny's LiDAR DTMs of Europe (sonny.4lima.de) harmonises *DTMs* only, not DSMs.

### Austria
- Nationwide DTM open (basemap.at). DSM: only Vienna at 0.5 m free. Rest of country DSM is commercial.

### New Zealand LINZ
- **Homepage:** https://data.linz.govt.nz/
- **Coverage:** Most of NZ, expanding.
- **Resolution:** 1 m DEM from LIDAR (DTM). DSM available for subsets.
- **License:** CC-BY 4.0.
- **Python:** LINZ Data Service WFS/WMS; also AWS Open Data Registry (`nz-elevation`) as COGs.

### Australia ELVIS
- **Homepage:** https://elevation.fsdf.org.au/
- **Coverage:** Coastal + major urban; not nationwide LIDAR. Geoscience Australia also publishes 1-sec SRTM-derived DEM-S nationally.
- **Resolution:** 1 m LIDAR where covered.
- **Limits:** 15 GB per request.
- **License:** CC-BY (varies by supplying state).

### Japan GSI
- **Homepage:** https://fgd.gsi.go.jp/
- **Resolution:** 5 m (DEM5A, ~70% coverage, urban/coastal), 10 m national (DEM10B). Both DTM. DSM is limited.
- **Python:** GSI Tile XML → raster conversion (see Leamon 2023 walkthrough).

### EU-DEM v1.1 (deprecated — note for completeness)
- 25 m pan-European DSM derived from SRTM+ASTER fusion. **No longer maintained.** Superseded by Copernicus DEM EEA-10 / GLO-30. Do not build against EU-DEM.

### Copernicus DEM EEA-10
- 10 m DSM for the 39 EEA countries. Free, CC-BY. Bridges the gap for European countries without national LIDAR. Access via Copernicus Data Space Ecosystem (free registration).

---

## Sources — Direct building heights (DSM fallback)

These are the critical layer when no LIDAR DSM is available. They attach a `height` attribute directly to the footprint, so the pipeline becomes `fetch_footprints → join_height → extrude` with no raster at all.

### Microsoft Global ML Building Footprints + Heights
- **Homepage:** https://planetarycomputer.microsoft.com/dataset/ms-buildings ; https://github.com/microsoft/GlobalMLBuildingFootprints
- **Coverage:** 1.5 B+ footprints globally. **Heights: partial** — ~4.2 M height estimates added Feb 2025 for Turkey, Greece, France, from Maxar + Vexcel 2017–2024 imagery. Growing but far from universal.
- **License:** ODbL.
- **Python:** `planetary-computer` + `pystac-client`, or direct geoparquet from GitHub releases.
- **Pipeline fit:** Where height is present, it's the best free per-footprint height outside LIDAR countries. Where absent, fall back to next layer.

### Overture Maps Buildings Theme
- **Homepage:** https://docs.overturemaps.org/guides/buildings/
- **Coverage:** Global compilation (OSM + Microsoft + Google + Esri + Zenodo) — GA as of April 2026.
- **Heights:** `height` (metres, to tallest point) and `num_floors` attributes in schema. **Coverage is spotty** — even Sydney downtown is missing heights for most footprints. Improving via Esri Community Maps and open LIDAR enrichment.
- **License:** CDLA Permissive 2.0 + ODbL for OSM-derived. Redistribution OK.
- **Python:** `overturemaps` CLI, or DuckDB `read_parquet('s3://overturemaps-us-west-2/release/.../theme=buildings/*')`. Also GeoParquet.
- **Pipeline fit:** Best "one-stop" building layer. Query by bbox, take height when present, cascade to next source when null.

### Google Open Buildings 2.5D Temporal
- **Homepage:** https://sites.research.google/gr/open-buildings/temporal/
- **Coverage:** Africa, South Asia, SE Asia, Latin America, Caribbean. ~58 M km². **Not** US/EU/AU/JP.
- **Resolution:** 4 m raster (presence, fractional count, height). Annual 2016–2023.
- **Accuracy:** MAE ~1.5 m in height (< one storey).
- **License:** CC-BY 4.0.
- **Python:** Earth Engine (`GOOGLE/Research/open-buildings-temporal/v1`) or direct GCS download.
- **Pipeline fit:** **Critical for Global South.** Zonal-stats the 4-m height raster onto a footprint (OSM/Overture) to get per-building height. This replaces the DSM−DTM step entirely in these regions.

### GHS-BUILT-H (JRC P2023A)
- **Homepage:** https://human-settlement.emergency.copernicus.eu/
- **Coverage:** **Truly global**, 100 m grid.
- **Resolution:** 100 m. Outputs AGBH (gross, m³/m²) and ANBH (net, metres).
- **Vintage:** 2018 reference year.
- **License:** CC-BY 4.0.
- **Python:** Earth Engine `JRC/GHSL/P2023A/GHS_BUILT_H` or direct raster download.
- **Pipeline fit:** **The global safety net.** Too coarse for per-building extrusion, but works as a neighbourhood-average height when you literally have nothing else. Use as last-resort: assign every footprint in a 100 m cell the same ANBH value. Visual quality is "blocky but correct order of magnitude."

### OSM `height` / `building:levels` tags
- **Coverage:** Sparse and uneven. Dense in mapped-by-enthusiasts regions (DE, NL, parts of UK/US cities), near-zero elsewhere.
- **Python:** Already inside any OSM fetch (Overture includes OSM-derived tags).
- **Pipeline fit:** First thing to check on any footprint. If present, use it. Convert levels to metres at ~3 m/level.

### Commercial (keyed) — Nearmap AI, Maxar Precision3D, Hexagon
- All offer building heights at sub-metre accuracy in covered cities.
- Nearmap AI `buildingHeights` layer: US + AU + NZ + CA + UK core coverage, REST API, paid key.
- Maxar Vexcel heights underlie the Microsoft dataset already — direct access via Vexcel is enterprise.
- **Pipeline fit:** Opportunistic BYOK slot. Not v1.

---

## Sources — Meta-catalogs (multi-source gateways)

### OpenTopography
- **Homepage:** https://opentopography.org/
- **What's there:** Copernicus GLO-30/90, NASADEM, SRTM GL1/GL3, AW3D30, GEBCO (bathymetry), US 3DEP LIDAR notebooks, 600+ community LIDAR datasets (many university surveys, some of which fill gaps in the national programmes).
- **Auth:** Free API key required since 2022 for global raster datasets.
- **Rate limits:** 500 calls / 24 h; per-dataset area caps (SRTM/COP90: 4.05 M km² per request).
- **License:** Pass-through of each source's licence. Derivatives from CC-BY sources are redistributable.
- **Python:** `bmi-topography` is the canonical wrapper.
- **Pipeline fit:** Our primary curator for DTM fetches. Single API, single key, multiple providers behind it.

### Microsoft Planetary Computer
- **Homepage:** https://planetarycomputer.microsoft.com/
- **What's there:** Copernicus DEM, ALOS, NASADEM, 3DEP lidar (point clouds + COG DSM/DTM), Microsoft Buildings, Sentinel, Landsat, many more. STAC-compliant.
- **Auth:** Free, optional token for higher quotas. `planetary-computer.sign()` for SAS URLs.
- **License:** Pass-through.
- **Python:** `pystac-client` + `planetary-computer` + `rasterio` is the canonical stack. Works for lazy, windowed reads.
- **Pipeline fit:** Primary for 3DEP DSM, Microsoft Buildings, Copernicus DEM. STAC-queryable by bbox makes lat/lon pipelines clean.

### Google Earth Engine
- **Coverage:** Essentially every open global dataset, including AHN4, UK LIDAR, GHSL, Copernicus DEM, Microsoft Buildings, Google Open Buildings 2.5D (**exclusively here for the 4-m raster**).
- **Auth:** Free account; commercial non-interactive use now requires a licensed tier (since 2023). **Caveat for Rook:** GEE's commercial licensing changes may block shipping this as a default provider to paying users. Verify before wiring in.
- **Python:** `earthengine-api`. Server-side computation model — different mental model from rasterio.
- **Pipeline fit:** Useful for Open Buildings 2.5D zonal stats (do it GEE-side, export small result). Risky as a default for commercial product.

### AWS Open Data Registry
- **What's there:** Copernicus DEM (`copernicus-dem-30m`), NZ elevation (`nz-elevation`), USGS 3DEP (via Planetary Computer), plus many imagery stacks.
- **Auth:** None (requester-pays never applies to these elevation buckets).
- **Python:** `rasterio` + boto3 unsigned. No throttles for well-behaved clients.
- **Pipeline fit:** Simplest path for Copernicus DEM and NZ. Zero-auth means zero key management.

### STAC Catalogs (generic)
- Increasingly the lingua franca. Planetary Computer, Element84 Earth Search, OpenTopography (partial), Copernicus Data Space all expose STAC.
- **Python:** `pystac-client` is interchangeable across all of them.
- **Pipeline fit:** Build the provider abstraction around a STAC client where possible; collapse many "providers" into one code path.

---

## Coverage gap map

**DTM — effectively solved globally.**
- GLO-30 covers everything, CC-BY, free. Use it as the floor.
- National 1 m DTM layered in where available: US, UK, NL, FR, NO, SE, DK (partially), IE, CH, parts of DE/AT/ES/IT, NZ, JP (10 m), AU coast.

**DSM at building scale (≤5 m) — archipelago.**
- Covered: UK, NL, FR, CH, NZ, US (partial), AU coastal, DE/AT urban. Japan has 5 m DTM but DSM is patchy.
- **Not covered (the desert):** all of Africa, most of South/SE Asia, Latin America, Middle East, Eastern Europe rural, Russia, most of Canada/Alaska interior, Greenland, Antarctica.
- **In the desert, you have no DSM.** You have three replacements: Microsoft heights (patchy), Google Open Buildings 2.5D (Global South only but excellent), GHS-BUILT-H 100 m (global, coarse).

**Direct heights — global but uneven.**
- Africa / S Asia / SE Asia / LatAm / Caribbean: Google Open Buildings 2.5D at 4 m is **better than any free DSM** for this purpose. Africa gap closed.
- Europe / US / AU: Microsoft heights + Overture + OSM levels, reinforced by national LIDAR.
- Middle East, Central Asia, Pacific: GHS-BUILT-H 100 m is the only universal backstop. Order-of-magnitude only.

---

## Recommended BYOK matrix for v1

**v1 minimum (no user key required):**

| Layer | Provider | Why |
|---|---|---|
| DTM | Copernicus GLO-30 via AWS (unsigned) | Global, free, CC-BY, trivial rasterio |
| National DSM | UK EA, NL AHN4, FR IGN, USGS 3DEP, NZ LINZ, CH swisstopo | Plugged in where lat/lon lands in-coverage |
| Heights fallback 1 | Overture buildings (bbox fetch, take `height` when present) | Single-source global, GA |
| Heights fallback 2 | Google Open Buildings 2.5D (Global South) | Fills the DSM desert at 4 m |
| Heights fallback 3 | GHS-BUILT-H 100 m | Universal last-resort |

**v1 opportunistic (BYOK slot, key-gated):**
- OpenTopography API key — unlocks higher-quota 30-m DEM fetches and curated LIDAR datasets.
- NASA Earthdata — NASADEM fallback.
- Google Earth Engine service account — for Open Buildings 2.5D zonal stats without local download.
- Copernicus Data Space account — for EEA-10 (10 m European DSM).

**v1 excluded (premium, out of scope):**
- Nearmap AI, Maxar Precision3D, Hexagon HxGN Content Program, Vexcel. All commercial, all high-cost. Document the slots; don't integrate.
- TanDEM-X 12 m — not redistributable in derivative form without an Airbus agreement.
- Any GEE usage that would trigger commercial licensing for Rook-at-scale. Defer until licensing posture is clarified.

**Architectural recommendation:** The pipeline's "height source" should be an abstract `HeightProvider` protocol with two implementations — `DSMMinusDTMProvider(dsm_source, dtm_source)` and `AttributeHeightProvider(feature_source)`. This way the LIDAR and no-LIDAR paths converge at the extrusion step, and new sources (commercial keys, new national LIDAR releases) plug in as new concrete providers without touching the extruder.

---

## Open questions

1. **Copernicus DEM licence migration (July 2025 → CC-BY 4.0):** confirm the current licence applies retroactively to the AWS `copernicus-dem-30m` bucket, not just Climate Data Store. Attribution string requirements differ. → fetch and read the LICENSE file in the S3 bucket at build time.
2. **Google Open Buildings 2.5D via GCS direct download vs Earth Engine:** does the GCS export path preserve full temporal resolution, or only annual snapshots? Need for per-year building-age analysis.
3. **Microsoft Buildings height coverage inventory:** is there a published country-by-country height-coverage table? Otherwise, the pipeline needs to probe empty-heights-rate per bbox and decide whether to cascade.
4. **Germany state-level LIDAR aggregation:** is there a single WMS/WCS endpoint covering the open Länder, or is 16-way integration required? Affects whether DE is a "covered country" in v1.
5. **GEE commercial licensing posture for Rook:** current Rook is BYOK, so arguably the user's GEE account is the one hitting quota. Does Google's TOS treat Rook as a "commercial application" even when every request uses the user's own credentials? Legal review needed before making GEE a default code path.
6. **3DEP DSM collection boundaries:** Planetary Computer's `3dep-lidar-dsm` coverage map vs DTM coverage — where is DSM available but DTM is not, and vice versa? Need a probe to pick the strongest available layer per query.
7. **Redistribution of derived `.3dm`:** all cited free sources (CC-BY / OGL / CC-0 / public domain) permit shipping derivative geometry. But attribution metadata needs to land *somewhere in the .3dm file* — User Text on the document? A `readme.txt` alongside? Design decision.

Sources:
- [Copernicus DEM — Copernicus Data Space Ecosystem](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM)
- [Copernicus DEM — AWS Open Data Registry](https://registry.opendata.aws/copernicus-dem/)
- [Copernicus GLO-30 — OpenTopography](https://portal.opentopography.org/raster?opentopoID=OTSDEM.032021.4326.3)
- [Copernicus licence migration to CC-BY (July 2025)](https://forum.ecmwf.int/t/cc-by-licence-to-replace-licence-to-use-copernicus-products-on-02-july-2025/13464)
- [OpenTopography API docs & rate limits](https://portal.opentopography.org/apidocs/)
- [OpenTopography API key announcement](https://opentopography.org/blog/introducing-api-keys-access-opentopography-global-datasets)
- [USGS 3DEP products](https://www.usgs.gov/3d-elevation-program/about-3dep-products-services)
- [Planetary Computer 3DEP LIDAR example](https://github.com/microsoft/PlanetaryComputerExamples/blob/main/datasets/3dep-lidar/3dep-lidar-cog-example.ipynb)
- [UK EA LIDAR DTM 1 m](https://environment.data.gov.uk/dataset/13787b9a-26a4-4775-8523-806d13af58fc)
- [UK EA LIDAR DSM 1 m](https://environment.data.gov.uk/dataset/9ba4d5ac-d596-445a-9056-dae3ddec0178)
- [Netherlands AHN4 DSM](https://data.europa.eu/data/datasets/36461-actueel-hoogtebestand-nederland-dsm-ahn4-)
- [AHN4 on Earth Engine](https://developers.google.com/earth-engine/datasets/catalog/AHN_AHN4)
- [France IGN LiDAR HD](https://geoservices.ign.fr/lidarhd)
- [Switzerland swissSURFACE3D](https://www.swisstopo.admin.ch/en/geodata/height/surface3d.html)
- [Australia ELVIS](https://elevation.fsdf.org.au/)
- [New Zealand LINZ elevation](https://www.linz.govt.nz/products-services/data/types-linz-data/elevation-data)
- [NZ Elevation — AWS Open Data](https://registry.opendata.aws/nz-elevation/)
- [Japan GSI elevation data guide](https://www.gpxz.io/blog/japan-dem-guide)
- [EU-DEM legacy (EEA)](https://www.eea.europa.eu/data-and-maps/data/copernicus-land-monitoring-service-eu-dem)
- [Microsoft Building Footprints — Planetary Computer](https://planetarycomputer.microsoft.com/dataset/ms-buildings)
- [Microsoft GlobalMLBuildingFootprints on GitHub](https://github.com/microsoft/GlobalMLBuildingFootprints)
- [Overture Maps buildings guide](https://docs.overturemaps.org/guides/buildings/)
- [Overture buildings schema](https://docs.overturemaps.org/schema/reference/buildings/building/)
- [Google Open Buildings 2.5D Temporal](https://sites.research.google/gr/open-buildings/temporal/)
- [Open Buildings 2.5D on Earth Engine](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_Research_open-buildings-temporal_v1)
- [GHS-BUILT-H on Earth Engine](https://developers.google.com/earth-engine/datasets/catalog/JRC_GHSL_P2023A_GHS_BUILT_H)
- [JRC GHSL Data Package 2023](https://human-settlement.emergency.copernicus.eu/datasets.php)
- [Sonny's LiDAR DTMs of Europe](https://sonny.4lima.de/)
- [JRC LIDAR open data in Europe report](https://publications.jrc.ec.europa.eu/repository/bitstream/JRC126223/jrc126223_jrc126223_lidaropensourcedata.pdf)
- [Vertical accuracy comparison — ASTER, AW3D30, SRTM, NASADEM, TanDEM-X (MDPI 2020)](https://www.mdpi.com/2072-4292/12/21/3482)
- [bmi-topography Python package](https://pypi.org/project/bmi-topography/)
