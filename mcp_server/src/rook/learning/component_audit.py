"""Component deprecation audit — cross-references GH ComponentServer with our catalog.

Usage:
    python -m rook.learning.component_audit [--port PORT] [--output audit_report.json]

Port is auto-discovered from %TEMP%/rook/ discovery files. Use --port to override.

Calls /gh/library?audit=true to get deprecated/hidden/quarantine components
from the live GH instance, then cross-references with our tiered_knowledge.json
and component notes to identify deprecated components in our catalog.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx
from ..bridge import NATIVE_CLIENT_HEADERS

from ..bridge import get_rhino_host
from ..runtime_paths import resolve_readable_knowledge_path, resolve_writable_knowledge_path

TIERED_PATH = resolve_readable_knowledge_path("gh", "tiered_knowledge.json")
NOTES_DIR = resolve_readable_knowledge_path("gh", "notes")
NOTES_WRITE_DIR = resolve_writable_knowledge_path("gh", "notes")


def _resolve_base_url(port: int | None = None) -> str:
    """Return base URL from explicit port or discovery."""
    if port:
        return f"http://127.0.0.1:{port}"
    url = get_rhino_host()
    if url is None:
        raise RuntimeError(
            "No Rhino instance discovered. "
            "Ensure Rhino is running with RookNative loaded, or use --port."
        )
    return url


def fetch_audit(port: int | None = None) -> dict:
    """Call /gh/library?audit=true and return deprecated components."""
    base = _resolve_base_url(port)
    resp = httpx.get(
        f"{base}/gh/library",
        params={"audit": "true"},
        timeout=60.0, headers=NATIVE_CLIENT_HEADERS
    )
    resp.raise_for_status()
    result = resp.json()
    if not result.get("success"):
        raise RuntimeError(f"Audit call failed: {result.get('data')}")
    return result["data"]


def fetch_all_components(port: int | None = None) -> list[dict]:
    """Fetch all non-deprecated components for replacement matching."""
    base = _resolve_base_url(port)
    resp = httpx.get(
        f"{base}/gh/library",
        params={"limit": "10000"},
        timeout=60.0, headers=NATIVE_CLIENT_HEADERS
    )
    resp.raise_for_status()
    result = resp.json()
    if not result.get("success"):
        return []
    return result.get("data", {}).get("components", [])


def load_catalog_guids() -> dict[str, dict]:
    """Load our tiered knowledge and return a GUID -> entry map."""
    if not TIERED_PATH.exists():
        print(f"Warning: {TIERED_PATH} not found")
        return {}

    with open(TIERED_PATH, "r", encoding="utf-8") as f:
        tiered = json.load(f)

    # Components are nested under the "components" key,
    # and the GUID is the dictionary key (not a field in the entry).
    components = tiered.get("components", {})
    guid_map: dict[str, dict] = {}
    for guid, entry in components.items():
        guid_map[guid.lower()] = {"name": entry.get("name", ""), **entry}
    return guid_map


def build_note_guid_index() -> dict[str, Path]:
    """Build GUID -> note file path index by scanning all comp_ note files.

    Note file names (e.g. comp_00671de7.json) are NOT derived from component
    GUIDs — the GUID is stored inside the file at type_data.guid.
    """
    guid_to_path: dict[str, Path] = {}
    for note_path in NOTES_DIR.glob("comp_*.json"):
        try:
            with open(note_path, "r", encoding="utf-8") as f:
                note = json.load(f)
            td_guid = note.get("type_data", {}).get("guid", "").lower()
            if td_guid:
                guid_to_path[td_guid] = note_path
        except Exception:
            continue
    return guid_to_path


def run_audit(port: int | None = None) -> dict:
    """Run the full audit and return a structured report."""
    base = _resolve_base_url(port)
    print(f"Fetching component audit from {base}...")
    audit_data = fetch_audit(port)

    total = audit_data.get("totalScanned", 0)
    deprecated_count = audit_data.get("deprecatedCount", 0)
    obsolete_count = audit_data.get("obsoleteCount", 0)
    hidden_count = audit_data.get("hiddenCount", 0)
    deprecated_components = audit_data["components"]

    print(f"GH ComponentServer: {total} total, {deprecated_count} deprecated "
          f"({obsolete_count} obsolete, {hidden_count} hidden)")

    # Build deprecated GUID set from audit results
    deprecated_guids: set[str] = set()
    gh_deprecated_by_guid: dict[str, dict] = {}
    for comp in deprecated_components:
        guid = (comp.get("guid") or "").lower()
        if guid:
            deprecated_guids.add(guid)
            gh_deprecated_by_guid[guid] = comp

    # Fetch all healthy (non-deprecated) components for replacement matching
    print("Fetching healthy components for replacement matching...")
    all_healthy = fetch_all_components(port)
    healthy_by_name: dict[str, list[dict]] = {}
    for comp in all_healthy:
        name = comp.get("name", "")
        if name:
            healthy_by_name.setdefault(name.lower(), []).append(comp)
    print(f"Healthy components: {len(all_healthy)}")

    # Load our catalog
    print("Loading catalog...")
    catalog_guids = load_catalog_guids()
    print(f"Catalog: {len(catalog_guids)} components with GUIDs")

    # Cross-reference
    deprecated_in_catalog: list[dict] = []
    missing_from_gh: list[dict] = []
    healthy: list[dict] = []

    for guid, entry in catalog_guids.items():
        if guid in deprecated_guids:
            gh_comp = gh_deprecated_by_guid.get(guid, {})
            # Find a non-deprecated replacement with the same name
            name = entry.get("name", "")
            replacement = None
            if name:
                candidates = healthy_by_name.get(name.lower(), [])
                for c in candidates:
                    c_guid = (c.get("guid") or "").lower()
                    if c_guid != guid:
                        replacement = c
                        break

            deprecated_in_catalog.append({
                "name": name,
                "guid": guid,
                "obsolete": gh_comp.get("obsolete", False),
                "exposure": gh_comp.get("exposure", 0),
                "exposure_label": gh_comp.get("exposureLabel", ""),
                "category": gh_comp.get("category", ""),
                "replacement_guid": (replacement.get("guid") or "").lower() if replacement else None,
                "replacement_name": replacement.get("name") if replacement else None,
            })
        elif guid not in deprecated_guids:
            # Check if it exists in healthy components
            found_healthy = any(
                (c.get("guid") or "").lower() == guid
                for comps in healthy_by_name.values()
                for c in comps
            )
            if found_healthy:
                healthy.append({"name": entry.get("name", ""), "guid": guid})
            else:
                missing_from_gh.append({
                    "name": entry.get("name", ""),
                    "guid": guid,
                    "note": "GUID not found in GH ComponentServer — plugin may not be loaded",
                })

    # Find deprecated GH components NOT in our catalog
    deprecated_not_cataloged = []
    for guid in deprecated_guids:
        if guid not in catalog_guids:
            comp = gh_deprecated_by_guid.get(guid, {})
            deprecated_not_cataloged.append({
                "name": comp.get("name", ""),
                "guid": guid,
                "exposure_label": comp.get("exposureLabel", ""),
            })

    report = {
        "summary": {
            "gh_total": total,
            "gh_obsolete": obsolete_count,
            "gh_hidden": hidden_count,
            "catalog_total": len(catalog_guids),
            "catalog_deprecated": len(deprecated_in_catalog),
            "catalog_missing_from_gh": len(missing_from_gh),
            "catalog_healthy": len(healthy),
            "deprecated_not_in_catalog": len(deprecated_not_cataloged),
        },
        "deprecated_in_catalog": sorted(deprecated_in_catalog, key=lambda x: x["name"]),
        "missing_from_gh": sorted(missing_from_gh, key=lambda x: x["name"]),
        "deprecated_not_in_catalog": sorted(deprecated_not_cataloged, key=lambda x: x["name"]),
    }

    return report


def print_report(report: dict) -> None:
    """Print a human-readable summary."""
    s = report["summary"]
    print()
    print("=" * 60)
    print("COMPONENT DEPRECATION AUDIT REPORT")
    print("=" * 60)
    print(f"GH ComponentServer: {s['gh_total']} components")
    print(f"  Obsolete: {s['gh_obsolete']}")
    print(f"  Hidden:   {s['gh_hidden']}")
    print()
    print(f"Our Catalog: {s['catalog_total']} components")
    print(f"  Healthy:              {s['catalog_healthy']}")
    print(f"  DEPRECATED:           {s['catalog_deprecated']}")
    print(f"  Missing from GH:      {s['catalog_missing_from_gh']}")
    print()

    if report["deprecated_in_catalog"]:
        print("-" * 60)
        print("DEPRECATED COMPONENTS IN OUR CATALOG:")
        print("-" * 60)
        for d in report["deprecated_in_catalog"]:
            repl = (f" -> replacement: {d['replacement_name']} ({d['replacement_guid']})"
                    if d.get("replacement_guid") else " -> NO REPLACEMENT FOUND")
            flags = []
            if d["obsolete"]:
                flags.append("OBSOLETE")
            if d["exposure"] & 16:
                flags.append("HIDDEN")
            if d["exposure"] & 8:
                flags.append("QUARANTINE")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            print(f"  {d['name']:<40} {d['guid'][:12]}...{flag_str}{repl}")

    if report["missing_from_gh"]:
        print()
        print("-" * 60)
        print(f"MISSING FROM GH ({s['catalog_missing_from_gh']} — plugin not loaded?):")
        print("-" * 60)
        for m in report["missing_from_gh"][:20]:
            print(f"  {m['name']:<40} {m['guid'][:12]}...")
        if s["catalog_missing_from_gh"] > 20:
            print(f"  ... and {s['catalog_missing_from_gh'] - 20} more")

    print()


def update_catalog(report: dict, dry_run: bool = False) -> int:
    """Update component notes with deprecated_by field. Returns count of updated notes."""
    deprecated = report["deprecated_in_catalog"]
    if not deprecated:
        print("No deprecated components to update.")
        return 0

    # Build GUID -> note file path index (note filenames are NOT GUIDs)
    print("Building note file index...")
    guid_to_path = build_note_guid_index()
    print(f"Indexed {len(guid_to_path)} note files by GUID")

    updated = 0
    for d in deprecated:
        guid = d["guid"]
        note_path = guid_to_path.get(guid)
        if not note_path:
            continue

        if dry_run:
            repl = f" -> {d['replacement_guid']}" if d.get("replacement_guid") else ""
            print(f"  Would update: {note_path.name} ({d['name']}){repl}")
            updated += 1
            continue

        with open(note_path, "r", encoding="utf-8") as f:
            note = json.load(f)

        note["deprecated"] = True
        note["deprecated_reason"] = d.get("exposure_label", "obsolete")
        if d.get("replacement_guid"):
            note["deprecated_by"] = d["replacement_guid"]
            note["deprecated_replacement_name"] = d["replacement_name"]

        NOTES_WRITE_DIR.mkdir(parents=True, exist_ok=True)
        output_path = NOTES_WRITE_DIR / note_path.name
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(note, f, indent=2, ensure_ascii=False)
        updated += 1

    action = "Would update" if dry_run else "Updated"
    print(f"{action} {updated} component notes with deprecation info.")
    return updated


def main():
    parser = argparse.ArgumentParser(description="Audit GH components for deprecation")
    parser.add_argument("--port", type=int, default=None, help="Rhino plugin port (auto-discovered if omitted)")
    parser.add_argument("--output", type=str, default=None, help="Save full report as JSON")
    parser.add_argument("--update", action="store_true", help="Update component notes with deprecated_by field")
    parser.add_argument("--dry-run", action="store_true", help="Show what --update would change without writing")
    args = parser.parse_args()

    report = run_audit(args.port)
    print_report(report)

    if args.output:
        out_path = Path(args.output)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"Full report saved to {out_path}")

    if args.update or args.dry_run:
        update_catalog(report, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
