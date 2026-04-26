# GIS BYOK — Geocoding Dossier

**Part of:** [2026-04-24-gis-byok-pipeline-research.md](2026-04-24-gis-byok-pipeline-research.md)
**Status:** research (2026-04-24)

## Summary

Ship Nominatim's public instance as the zero-setup v1 default (forward + reverse only, polite rate-limited, branded `User-Agent`), and expose a keyed registry of **LocationIQ**, **Geoapify**, and **Mapbox (Permanent)** as the first-class power-user options. Nominatim covers 95% of the casual "drop in a lat/lon for Baker Street" case with zero friction; the three keyed providers unlock autocomplete, higher throughput, and — critically — a license that permits the project-file storage our pipeline *must* do.

## Providers

### Nominatim (OSM public instance)
- **Homepage:** https://nominatim.openstreetmap.org/
- **Coverage:** Global, OSM-derived. Strong where OSM is mature (EU, NA, Japan, urban APAC). Noticeably weaker in rural US (no parcel data), parts of Africa, rural SEA, and Latin America beyond major cities.
- **Forward / reverse / autocomplete:** Forward yes, reverse yes, **no autocomplete** on the public instance.
- **Auth:** None.
- **License:** Data ODbL. Results can be cached/stored freely — **this is the one major provider where project-file storage is unambiguously permitted**.
- **Rate limits / free tier:** Hard cap **1 req/s**, no bulk/grid/systematic queries, no heavy use. Requires identifying `User-Agent` OR `Referer`; stock library UAs are explicitly rejected. Violators get banned by IP.
- **Pricing:** Free.
- **Python access:** `geopy.geocoders.Nominatim(user_agent="rook/<version>")`. Direct REST is fine too — the rate-limit is the constraint, not the client.
- **Data source:** OSM.
- **Pipeline fit:** Perfect for v1 default *if* we throttle ourselves to ≤1 req/s and set a real UA. Unsuitable for batch jobs, autocomplete UIs, or any workflow that fires >60 geocodes/minute. If a power user wants a site-survey pipeline that buffers 200 addresses, push them to a keyed provider or a self-hosted Nominatim.

### LocationIQ
- **Homepage:** https://locationiq.com/
- **Coverage:** Global, primarily OSM + some enhanced US/EU sources.
- **Forward / reverse / autocomplete:** All three, including a dedicated autocomplete endpoint.
- **Auth:** Free key (no card required).
- **License:** Permissive — caching and storing results is allowed on all paid plans and the free plan (uncommon generosity among keyed providers).
- **Rate limits / free tier:** Free tier ≈ **5,000 req/day** (~150k/mo), 2 req/s.
- **Pricing:** $49/mo for 10k/day; scales to $950/mo for 1M/day. Roughly **$0.15–$0.50 per 1k** at mid-tier.
- **Python access:** `geopy.geocoders.LocationIQ(api_key=...)`. Direct REST also clean.
- **Data source:** OSM with some proprietary enrichment.
- **Pipeline fit:** Best keyed free tier for Rook users who want zero cost but also zero friction with rate-limits. Storage-permissive license is the tiebreaker against Mapbox.

### Geoapify
- **Homepage:** https://www.geoapify.com/
- **Coverage:** Global OSM + OpenAddresses + GeoNames fusion.
- **Forward / reverse / autocomplete:** All three.
- **Auth:** Free key.
- **License:** Caching/storage permitted per their ToS (with attribution). Derived from OSM so ODbL share-alike applies to bulk dumps.
- **Rate limits / free tier:** **3,000 credits/day**, 5 req/s on free tier (1 forward geocode = 1 credit).
- **Pricing:** Credit bundles from ~$75/mo for 300k credits. ~$0.25 per 1k at mid-tier.
- **Python access:** Direct REST. `geopy` has a `Geoapify` provider but the REST API is simpler.
- **Data source:** OSM + OpenAddresses + GeoNames.
- **Pipeline fit:** Clean alternative to LocationIQ; slightly better autocomplete UX, slightly smaller free tier.

### Mapbox Geocoding
- **Homepage:** https://www.mapbox.com/geocoding
- **Coverage:** Global, proprietary blend with strong US/EU/urban coverage, excellent ranking quality.
- **Forward / reverse / autocomplete:** All three, very strong autocomplete.
- **Auth:** Key required.
- **License:** **Split into two SKUs** — this is the trap.
  - **Temporary Geocoding**: 100k/mo free, $0.45–$0.75 per 1k after. Forbids *any* caching/storage; each call must be triggered by a live user action. Returned coordinates cannot be saved.
  - **Permanent Geocoding**: $5 per 1k, no free tier. Results may be stored and reused in databases/project files but may not be redistributed or sublicensed.
- **Python access:** Direct REST. `mapbox-sdk-py` exists but is thin.
- **Data source:** Proprietary (OSM + commercial + Mapbox edits).
- **Pipeline fit:** Rook *must* use the Permanent SKU. A site-generation pipeline that writes the lat/lon into a `.3dm` file or filename is "storage" under Mapbox's definition. Temporary SKU would silently violate ToS.

### Google Geocoding API
- **Homepage:** https://developers.google.com/maps/documentation/geocoding
- **Coverage:** Global, gold-standard accuracy especially in NA/EU/APAC metros, best-in-class for rural addresses and POI disambiguation.
- **Forward / reverse / autocomplete:** All three (autocomplete via Places API, separately billed).
- **Auth:** Key + enabled billing (card required, even for free tier).
- **License:** **Caching forbidden beyond 30 days.** Results may not be displayed on non-Google maps. Coordinates may be temporarily cached for performance but not stored long-term.
- **Rate limits / free tier:** Per-SKU free cap (~10k calls/mo on Geocoding Essentials as of March 2025 pricing reset).
- **Pricing:** **$5 per 1k** up to 100k/mo, $4 per 1k above.
- **Python access:** `googlemaps` official SDK or direct REST.
- **Data source:** Proprietary Google.
- **Pipeline fit:** **Do not ship as default.** The 30-day cache limit is incompatible with Rook writing lat/lon into project files that persist for years. Offer only as a keyed option with a clear warning in the BYOK contract UI.

### HERE Geocoding
- **Homepage:** https://developer.here.com/
- **Coverage:** Global, strong automotive/commercial coverage, routing-grade quality.
- **Forward / reverse / autocomplete:** All three.
- **Auth:** Key + account.
- **License:** **Caching gated by Enterprise license (~$10k/yr).** Freemium tier prohibits storing results.
- **Rate limits / free tier:** 250k transactions/mo free.
- **Pricing:** ~$1 per 1k after free tier (6% increase April 2026).
- **Python access:** Direct REST; `here-location-services-python` SDK.
- **Data source:** Proprietary HERE.
- **Pipeline fit:** Same storage problem as Google. Big free tier is tempting but incompatible with our use-case without enterprise licensing. Skip for v1.

### Azure Maps (absorbs Bing Maps)
- **Homepage:** https://azure.microsoft.com/products/azure-maps/
- **Coverage:** Global, TomTom-backed data.
- **Forward / reverse / autocomplete:** All three.
- **Auth:** Azure account + subscription key.
- **License:** Storage permitted under Azure Maps ToS (more permissive than Google/HERE).
- **Rate limits / free tier:** Free S0 tier includes modest monthly quota (varies by SKU).
- **Pricing:** ~$4.50 per 1k at higher tiers.
- **Python access:** Direct REST, `azure-maps-search` SDK.
- **Data source:** TomTom.
- **Pipeline fit:** Viable but requires Azure account setup — high friction for our target user (Rhino architect, not DevOps). Bing Maps Basic **retired June 30, 2025**; any docs pointing to Bing are stale.

### TomTom Geocoding
- **Homepage:** https://developer.tomtom.com/
- **Coverage:** Global, routing-grade.
- **Forward / reverse / autocomplete:** All three.
- **Auth:** Free key.
- **License:** Permits display and ephemeral caching; long-term storage requires paid plan / explicit opt-in.
- **Rate limits / free tier:** **2,500 free transactions/day**.
- **Pricing:** ~$0.50 per 1k.
- **Python access:** Direct REST.
- **Data source:** Proprietary TomTom.
- **Pipeline fit:** Decent free tier, simpler onboarding than Azure. Storage terms are murkier than LocationIQ/Geoapify — verify before shipping.

### Esri ArcGIS World Geocoder
- **Homepage:** https://developers.arcgis.com/
- **Coverage:** Global, strongest US commercial address coverage, parcel-level in many regions.
- **Forward / reverse / autocomplete:** All three.
- **Auth:** ArcGIS developer account + API key.
- **License:** **Requires `forStorage=true` flag** on `findAddressCandidates` calls to legally persist results. Higher billable rate applies when that flag is set.
- **Rate limits / free tier:** 20k free geocodes/mo (no-store) in the Location Platform free tier.
- **Pricing:** Stored geocodes billed separately at higher per-transaction cost.
- **Python access:** `arcgis` SDK (heavy) or direct REST (recommended).
- **Data source:** Proprietary Esri + TomTom + partners.
- **Pipeline fit:** Best choice for architecture/AEC users who already have ArcGIS credentials (many do). Explicit `forStorage` flag is actually the cleanest licensing model in the industry — predictable and honest.

### Geocode Earth
- **Homepage:** https://geocode.earth/
- **Coverage:** Global, OSM + OpenAddresses + WhosOnFirst.
- **Forward / reverse / autocomplete:** All three (Pelias-backed).
- **Auth:** Key.
- **License:** Permissive — operated by the Pelias core team.
- **Rate limits / free tier:** Free discounts for FOSS projects; paid plans from ~$100/mo.
- **Pricing:** Similar to LocationIQ/Geoapify mid-tier.
- **Python access:** Direct REST (Pelias API).
- **Data source:** OSM + OpenAddresses + WhosOnFirst.
- **Pipeline fit:** Strong ethical choice (funds Pelias OSS); no free tier for general use makes it hard to recommend as v1 default. Good for users who want to support open-source geocoding.

### Photon (komoot public instance)
- **Homepage:** https://photon.komoot.io/
- **Coverage:** Global, OSM-based, strength in typo-tolerance and autocomplete.
- **Forward / reverse / autocomplete:** All three, **excellent autocomplete** (its original design goal).
- **Auth:** None.
- **License:** Data ODbL (OSM). Public instance usage terms ask for "reasonable" use only.
- **Rate limits / free tier:** No published hard limit; effectively ~1 req/s; heavy use will be throttled or banned.
- **Pricing:** Free public, self-host recommended for production.
- **Python access:** Direct REST; `geopy.geocoders.Photon`.
- **Data source:** OSM.
- **Pipeline fit:** Use for autocomplete in Assist-mode address picker UIs where Nominatim can't help. Not a production backbone.

### Self-hosted options (mentioned, not registry candidates)
- **Nominatim (self-hosted):** Docker image available, ~900 GB planet DB, 64 GB RAM recommended. Removes all rate-limit constraints. Correct choice for a firm that geocodes thousands of addresses/day.
- **Pelias (Docker):** `pelias/docker` compose stack pulls OSM + OpenAddresses + WhosOnFirst + GeoNames. Heavier to operate than Nominatim but better quality and autocomplete.
- **OpenAddresses:** Raw address→coordinate CSV corpus, not a service. Useful as a Pelias feed or as a bulk local lookup for known jurisdictions.

## Accuracy and coverage notes

- **Urban NA/EU**: All providers converge within ~10m. Choice doesn't matter much for Manhattan, Paris, or Berlin.
- **Rural US**: Google and Esri dominate (parcel data). OSM-based providers (Nominatim, Photon, Geoapify, LocationIQ, Geocode Earth) degrade to ZIP centroid or road midpoint.
- **Africa, rural SEA, rural Latin America**: Everyone is weaker. OSM providers are often *better* than commercial ones because local mappers outperform stale proprietary datasets. Google remains decent in major cities only.
- **Address density**: For an architecture-pipeline use case (user drops an address for a project site), a 50m error at the geocoding step is usually acceptable — the user eyeballs it on the LIDAR preview and adjusts. This tolerance is why Nominatim is viable as v1 default despite lower accuracy than Google/Esri.
- **Ambiguity handling**: Mapbox and Google return the best-ranked first result with confidence scores. Nominatim returns multiple candidates with less useful ranking. For a Rook pipeline, surface the top 3 candidates and let the user confirm before running the expensive LIDAR/footprint fetch.

## License gotchas (CRITICAL for BYOK contract)

Rook writes the geocoded lat/lon into filenames, `.3dm` project documents, and user-facing artifacts. That is **caching/storage** under every major provider's ToS. Per-provider:

| Provider | Storage of result lat/lon | Action for Rook |
|---|---|---|
| **Nominatim** | Allowed (ODbL) | OK — default |
| **LocationIQ** | Allowed | OK — recommend |
| **Geoapify** | Allowed (attribution) | OK — recommend |
| **Mapbox Temporary** | **Forbidden** | **Block in BYOK UI** |
| **Mapbox Permanent** | Allowed ($5/1k) | OK — surface as the paid Mapbox path |
| **Google** | Forbidden >30 days | Warn aggressively; not recommended |
| **HERE Freemium** | Forbidden | Not recommended |
| **Azure Maps** | Allowed per ToS | OK |
| **TomTom** | Ephemeral OK, long-term needs paid plan | Warn |
| **Esri** | Requires `forStorage=true` flag (higher price) | OK if we set the flag |
| **Geocode Earth** | Allowed | OK |
| **Photon public** | Ephemeral only (OSM-data cache OK) | Avoid for storage path |

The Rook BYOK contract must make this explicit: each provider entry in the registry carries a `storage_allowed: true|false|paid_tier_only` flag, and the pipeline refuses to write results to disk when the active provider is `false`. For Mapbox specifically we should expose **Temporary** and **Permanent** as two registry entries, not one, so the user's chosen SKU lines up with the license.

A second subtlety: even providers that permit storage often require attribution in derived outputs. For Rook, a comment in the `.3dm` usertext (`geocoded_by: "Nominatim (OSM)"` with the query date) satisfies this cleanly.

## Recommended BYOK matrix for v1

- **v1 default (no key required):** **Nominatim public instance**, with a hard-coded 1 req/s throttle, branded `User-Agent: Rook/<version> (https://github.com/bringfire/Rook)`, and a visible note in the UI that heavy use should switch to a keyed provider or self-host.
- **v1 keyed providers (registry):**
  1. **LocationIQ** — best free-tier-with-key, storage-permissive, full autocomplete.
  2. **Geoapify** — parallel alternative, slightly different data blend, good for users who prefer OpenAddresses coverage.
  3. **Mapbox Permanent Geocoding** — the paid, storage-legal option for users who already use Mapbox and want gold-standard ranking. Must appear **separate from** any Temporary Mapbox key entry.
- **Opportunistic (surface but don't lead with):** Esri ArcGIS (for AEC users with existing credentials), Geocode Earth (for FOSS-supporting users), Photon (autocomplete-only adjunct).
- **Excluded from v1:** Google Geocoding (30-day cache limit fundamentally incompatible with our artifact-persistence model), HERE (caching requires enterprise license), Azure Maps (onboarding friction too high for the Rhino-architect persona), TomTom (storage terms murky), Bing Maps (retired June 2025).

## Open questions

- Does the Rook BYOK UI need to distinguish "session cache" (in-memory, fine under Google/HERE) from "project storage" (persistent, forbidden under Google/HERE) as two separate license gates, or is the one-shot pipeline so write-heavy that the distinction is moot?
- Should v1 ship a self-hosted-Nominatim adapter (point-at-URL) alongside the public-instance default? Low effort, high value for architecture firms that already run one.
- How do we attribute in a Rhino document? `Document.Strings["rook.geocoder.provider"] = "Nominatim"` is the cleanest slot; confirm with a pass through `rhino_usertext_document_set`.
- For autocomplete UIs (address picker): is Photon-public acceptable for the session's keystroke-by-keystroke calls (they're ephemeral), while the final confirmed address is re-geocoded through the storage-legal provider for persistence? This "two-provider split" pattern sidesteps most license traps but doubles registry complexity.
- `geopy` wraps most of these but does **not** solve rate-limiting (user must add `RateLimiter`), auth plumbing, or per-provider storage-flag differences (e.g. Esri's `forStorage=true`). Plan on a thin Rook-side adapter layer per provider rather than leaning hard on `geopy` as the abstraction.
