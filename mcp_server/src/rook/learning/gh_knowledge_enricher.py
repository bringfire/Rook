"""
GH Knowledge Enricher

Merges training patterns from GrasshopperHowtos into the tiered knowledge store.
Adds:
1. Verified component GUIDs from real definitions
2. Common wiring patterns for auto-wiring
3. Typical slider configurations for sensible defaults
"""

import json
from ..runtime_paths import resolve_readable_knowledge_path, resolve_writable_knowledge_path


def load_training_patterns() -> dict:
    """Load extracted training patterns."""
    path = resolve_readable_knowledge_path("gh", "training_patterns.json")
    with open(path) as f:
        return json.load(f)


def load_tiered_knowledge() -> dict:
    """Load existing tiered knowledge."""
    path = resolve_readable_knowledge_path("gh", "tiered_knowledge.json")
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {"components": {}, "wiring_patterns": {}, "slider_defaults": {}}


def save_tiered_knowledge(data: dict):
    """Save enriched tiered knowledge."""
    path = resolve_writable_knowledge_path("gh", "tiered_knowledge.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"Saved enriched knowledge to {path}")


def enrich_knowledge():
    """Merge training patterns into tiered knowledge."""
    training = load_training_patterns()
    knowledge = load_tiered_knowledge()

    # Track statistics
    stats = {
        "guids_added": 0,
        "guids_verified": 0,
        "wiring_patterns_added": 0,
        "slider_configs_added": 0
    }

    # 1. Enrich component GUIDs from training data
    if "verified_guids" not in knowledge:
        knowledge["verified_guids"] = {}

    for comp in training.get("top_components", []):
        guid = comp["guid"]
        name = comp["name"]
        count = comp["count"]

        if name not in knowledge["verified_guids"]:
            knowledge["verified_guids"][name] = {
                "guid": guid,
                "usage_count": count,
                "source": "GrasshopperHowtos"
            }
            stats["guids_added"] += 1
        else:
            # Verify existing GUID matches
            existing = knowledge["verified_guids"][name]
            if existing.get("guid") == guid:
                existing["usage_count"] = max(existing.get("usage_count", 0), count)
                stats["guids_verified"] += 1
            else:
                # Conflict - keep the one with higher usage
                if count > existing.get("usage_count", 0):
                    existing["guid"] = guid
                    existing["usage_count"] = count
                    existing["source"] = "GrasshopperHowtos (updated)"

    # 2. Add common wiring patterns
    if "common_wiring" not in knowledge:
        knowledge["common_wiring"] = {}

    for pattern in training.get("common_wiring", []):
        source = pattern["source"]
        target = pattern["target"]
        param = pattern["param"]
        count = pattern["count"]

        if source not in knowledge["common_wiring"]:
            knowledge["common_wiring"][source] = []

        # Check if pattern already exists
        existing = [p for p in knowledge["common_wiring"][source]
                    if p.get("target") == target and p.get("param") == param]
        if not existing:
            knowledge["common_wiring"][source].append({
                "target": target,
                "param": param,
                "count": count
            })
            stats["wiring_patterns_added"] += 1

    # 3. Add slider configuration defaults
    if "slider_defaults" not in knowledge:
        knowledge["slider_defaults"] = {}

    for context, config in training.get("slider_configurations", {}).items():
        if context not in knowledge["slider_defaults"]:
            knowledge["slider_defaults"][context] = {
                "typical_min": round(config["typical_min"], 2),
                "typical_max": round(config["typical_max"], 2),
                "typical_value": round(config["typical_value"], 2),
                "sample_count": config["count"]
            }
            stats["slider_configs_added"] += 1

    # 4. Add training metadata
    knowledge["training_metadata"] = {
        "source": "GrasshopperHowtos by jhorikawa",
        "definitions_analyzed": training["summary"]["definitions_parsed"],
        "total_component_instances": training["summary"]["total_component_instances"],
        "unique_components": training["summary"]["unique_components"]
    }

    save_tiered_knowledge(knowledge)

    print("\n=== Enrichment Statistics ===")
    print(f"GUIDs added: {stats['guids_added']}")
    print(f"GUIDs verified: {stats['guids_verified']}")
    print(f"Wiring patterns added: {stats['wiring_patterns_added']}")
    print(f"Slider configs added: {stats['slider_configs_added']}")

    return stats


def generate_guid_lookup() -> dict:
    """Generate a simple name -> GUID lookup table."""
    training = load_training_patterns()
    lookup = {}
    for comp in training.get("top_components", []):
        lookup[comp["name"]] = comp["guid"]
    return lookup


def get_wiring_suggestions(component_name: str) -> list[dict]:
    """Get suggested wiring targets for a component."""
    training = load_training_patterns()
    suggestions = []
    for pattern in training.get("common_wiring", []):
        if pattern["source"] == component_name:
            suggestions.append({
                "target": pattern["target"],
                "param": pattern["param"],
                "count": pattern["count"]
            })
    return sorted(suggestions, key=lambda x: x["count"], reverse=True)


def get_slider_defaults(context: str) -> dict:
    """Get default slider values for a given context (e.g., 'Series.Count')."""
    training = load_training_patterns()
    configs = training.get("slider_configurations", {})
    if context in configs:
        cfg = configs[context]
        return {
            "min": round(cfg["typical_min"], 2),
            "max": round(cfg["typical_max"], 2),
            "value": round(cfg["typical_value"], 2)
        }
    return None


if __name__ == "__main__":
    enrich_knowledge()

    # Show some examples
    print("\n=== Sample Wiring Suggestions ===")
    for comp in ["Number Slider", "Unit Z", "Bounds"]:
        suggestions = get_wiring_suggestions(comp)[:3]
        if suggestions:
            print(f"\n{comp} typically wires to:")
            for s in suggestions:
                print(f"  -> {s['target']}.{s['param']} ({s['count']}x)")

    print("\n=== Sample Slider Defaults ===")
    for ctx in ["Series.Count", "Range.Steps", "Construct Domain.Domain end"]:
        defaults = get_slider_defaults(ctx)
        if defaults:
            print(f"{ctx}: min={defaults['min']}, max={defaults['max']}, value={defaults['value']}")
