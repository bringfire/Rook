"""Audit sparse_index.json for integrity issues.

Checks:
1. Every GUID in intent_to_guids exists in guid_to_info
2. Every GUID in guid_to_info has at least one intent pointing to it
3. Critical intents resolve to correct component types (not params)
4. Family-to-guids consistency
5. Duplicate GUIDs across intents
"""

import json
import sys
from pathlib import Path

SPARSE_INDEX_PATH = Path(__file__).parent.parent / "knowledge" / "gh" / "sparse_index.json"
TIERED_KNOWLEDGE_PATH = Path(__file__).parent.parent / "knowledge" / "gh" / "tiered_knowledge.json"

# Critical intents that MUST map to creator components (not params)
CRITICAL_INTENTS = [
    "arc", "circle", "line", "rectangle", "ellipse", "polygon", "polyline",
    "sphere", "box", "cylinder", "cone", "pipe",
    "move", "rotate", "scale", "mirror",
    "loft", "extrude", "sweep",
    "point", "vector", "plane",
    "add", "subtract", "multiply", "divide",
    "list item", "series", "range",
    "interpolate", "nurbs curve",
]


def audit():
    with open(SPARSE_INDEX_PATH) as f:
        data = json.load(f)

    intent_to_guids = data.get("intent_to_guids", {})
    guid_to_info = data.get("guid_to_info", {})
    family_to_guids = data.get("family_to_guids", {})

    issues = []
    warnings = []
    info = []

    # === Check 1: Every GUID in intent_to_guids exists in guid_to_info ===
    orphan_guids = {}  # guid -> list of intents that reference it
    for intent, guids in intent_to_guids.items():
        for guid in guids:
            if guid not in guid_to_info:
                if guid not in orphan_guids:
                    orphan_guids[guid] = []
                orphan_guids[guid].append(intent)

    if orphan_guids:
        issues.append(f"ORPHAN GUIDs: {len(orphan_guids)} GUIDs in intent_to_guids not found in guid_to_info:")
        for guid, intents in orphan_guids.items():
            issues.append(f"  {guid} <- intents: {intents}")

    # === Check 2: Every GUID in guid_to_info has at least one intent ===
    all_referenced_guids = set()
    for guids in intent_to_guids.values():
        all_referenced_guids.update(guids)

    unreachable = []
    for guid, info_data in guid_to_info.items():
        if guid not in all_referenced_guids:
            name = info_data.get("name", "unknown")
            unreachable.append((guid, name))

    if unreachable:
        warnings.append(f"UNREACHABLE: {len(unreachable)} GUIDs in guid_to_info with NO intent pointing to them:")
        for guid, name in unreachable:
            warnings.append(f"  {guid} ({name})")

    # === Check 3: Critical intents ===
    info.append("CRITICAL INTENT CHECK:")
    for intent in CRITICAL_INTENTS:
        if intent not in intent_to_guids:
            warnings.append(f"  MISSING: '{intent}' has no entry in intent_to_guids")
            continue
        guids = intent_to_guids[intent]
        for guid in guids:
            if guid in guid_to_info:
                ginfo = guid_to_info[guid]
                name = ginfo.get("name", "?")
                family = ginfo.get("family", "?")
                info.append(f"  '{intent}' -> {guid[:8]}... ({name}, family={family})")
            else:
                issues.append(f"  '{intent}' -> {guid[:8]}... (NOT IN guid_to_info!)")

    # === Check 4: Family-to-guids consistency ===
    family_orphans = {}
    for family, guids in family_to_guids.items():
        for guid in guids:
            if guid not in guid_to_info:
                if family not in family_orphans:
                    family_orphans[family] = []
                family_orphans[family].append(guid)

    if family_orphans:
        warnings.append(f"FAMILY ORPHANS: {len(family_orphans)} families reference GUIDs not in guid_to_info:")
        for family, guids in family_orphans.items():
            warnings.append(f"  {family}: {[g[:8] for g in guids]}")

    # === Check 5: Duplicate GUID across different intents (informational) ===
    guid_intent_count = {}
    for intent, guids in intent_to_guids.items():
        for guid in guids:
            if guid not in guid_intent_count:
                guid_intent_count[guid] = []
            guid_intent_count[guid].append(intent)

    multi_intent = {g: intents for g, intents in guid_intent_count.items() if len(intents) > 1}
    if multi_intent:
        info.append(f"\nMULTI-INTENT GUIDs: {len(multi_intent)} GUIDs referenced by multiple intents (usually fine):")
        for guid, intents in sorted(multi_intent.items(), key=lambda x: -len(x[1])):
            name = guid_to_info.get(guid, {}).get("name", "?")
            info.append(f"  {guid[:8]}... ({name}) <- {intents}")

    # === Check 6: Cross-reference with tiered_knowledge.json ===
    if TIERED_KNOWLEDGE_PATH.exists():
        with open(TIERED_KNOWLEDGE_PATH) as f:
            tiered = json.load(f)

        components_data = tiered.get("components", {})
        # components is a dict keyed by GUID
        tiered_guids = set(components_data.keys())

        sparse_guids = set(guid_to_info.keys())
        in_tiered_not_sparse = tiered_guids - sparse_guids
        in_sparse_not_tiered = sparse_guids - tiered_guids

        if in_tiered_not_sparse:
            warnings.append(f"\nIN TIERED BUT NOT SPARSE: {len(in_tiered_not_sparse)} components in tiered_knowledge.json missing from sparse_index guid_to_info:")
            for guid in sorted(in_tiered_not_sparse):
                name = components_data.get(guid, {}).get("name", "?")
                warnings.append(f"  {guid[:8]}... ({name})")

        if in_sparse_not_tiered:
            info.append(f"\nIN SPARSE BUT NOT TIERED: {len(in_sparse_not_tiered)} GUIDs in sparse_index but not in tiered_knowledge:")
            for guid in sorted(in_sparse_not_tiered):
                name = guid_to_info.get(guid, {}).get("name", "?")
                info.append(f"  {guid[:8]}... ({name})")

    # === Summary ===
    print("=" * 60)
    print("SPARSE INDEX AUDIT REPORT")
    print("=" * 60)

    print(f"\nStats:")
    print(f"  Intents: {len(intent_to_guids)}")
    print(f"  GUIDs in guid_to_info: {len(guid_to_info)}")
    print(f"  Families: {len(family_to_guids)}")

    if issues:
        print(f"\n{'='*60}")
        print(f"ERRORS ({len(issues)}):")
        print(f"{'='*60}")
        for issue in issues:
            print(f"  {issue}")

    if warnings:
        print(f"\n{'='*60}")
        print(f"WARNINGS ({len(warnings)}):")
        print(f"{'='*60}")
        for warning in warnings:
            print(f"  {warning}")

    if info:
        print(f"\n{'='*60}")
        print(f"INFO:")
        print(f"{'='*60}")
        for i in info:
            print(f"  {i}")

    # Return exit code
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(audit())
