"""Model-facing Grasshopper authoring-route admission.

The raw Grasshopper creation primitive is intentionally policy-neutral.  This
module owns the small public boundary that routes the two supported modern
script component identities to ``gh_create_script`` before target mutation.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping
from uuid import UUID


GH_SCRIPT_LANGUAGE_CONFIGS: dict[str, dict[str, Any]] = {
    "python": {
        "guid": "719467e6-7cf5-4848-99b0-c5dd57e5442c",
        "default_name": "Python 3 Script",
        "component_label": "Python 3 Script",
        "names": ("Python 3 Script", "Py3"),
        "alias": "gh_create_python_script",
    },
    "csharp": {
        "guid": "b6ba1144-02d6-4a2d-b53c-ec62e290eeb7",
        "default_name": "C# Script",
        "component_label": "C# Script",
        "names": ("C# Script", "C#"),
        "alias": "gh_create_csharp_script",
    },
}

MODEL_FACING_COMPONENT_CREATION_ROUTES = frozenset({
    "gh_edit",
    "gh_explore_component",
    "gh_explore_deep",
    "gh_investigate",
})


def _dotnet_guid_forms(canonical: str) -> frozenset[str]:
    parsed = UUID(canonical)
    compact = parsed.hex
    dashed = str(parsed)
    node_bytes = parsed.node.to_bytes(6, "big")
    data4 = (parsed.clock_seq_hi_variant, parsed.clock_seq_low, *node_bytes)
    x_form = (
        f"{{0x{parsed.time_low:08x},0x{parsed.time_mid:04x},"
        f"0x{parsed.time_hi_version:04x},"
        "{" + ",".join(f"0x{value:02x}" for value in data4) + "}}"
    )
    return frozenset({compact, dashed, "{" + dashed + "}", "(" + dashed + ")", x_form})


def _normalize_guid_text(value: str) -> str:
    return "".join(value.split()).casefold()


_SCRIPT_IDENTITIES = tuple(
    {
        "language": language,
        "guid": config["guid"],
        "guid_forms": frozenset(
            _normalize_guid_text(form) for form in _dotnet_guid_forms(config["guid"])
        ),
        "names": frozenset(name.casefold() for name in config["names"]),
        "alias": config["alias"],
    }
    for language, config in GH_SCRIPT_LANGUAGE_CONFIGS.items()
)


def _classify_component_selector(
    component: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, str]] | None:
    guid = component.get("guid")
    if isinstance(guid, str) and guid:
        normalized = _normalize_guid_text(guid)
        for identity in _SCRIPT_IDENTITIES:
            if normalized in identity["guid_forms"]:
                return identity, {"kind": "guid", "value": guid}

    name = component.get("name")
    if isinstance(name, str) and name:
        normalized = name.casefold()
        for identity in _SCRIPT_IDENTITIES:
            if normalized in identity["names"]:
                return identity, {"kind": "name", "value": name}

    return None


def _build_script_handoff(
    source_tool: str,
    request: Mapping[str, Any],
    identity: Mapping[str, Any],
    selector: Mapping[str, str],
) -> dict[str, Any]:
    language = str(identity["language"])
    guid = str(identity["guid"])
    message = (
        f"handoff_required: {source_tool} selected a {language} script component "
        f"({guid}). Call gh_create_script with language=\"{language}\" so source "
        "and pins are created through the dedicated authoring pipeline."
    )
    return {
        "success": False,
        "_is_handoff": True,
        "data": {
            "code": "script_component_requires_dedicated_tool",
            "handoff_required": True,
            "source_tool": source_tool,
            "selector": dict(selector),
            "component_guid": guid,
            "recommended_tool": "gh_create_script",
            "recommended_language": language,
            "alias_tool": str(identity["alias"]),
            "request": deepcopy(dict(request)),
            "message": message,
        },
    }


def resolved_script_handoff(
    source_tool: str,
    request: Mapping[str, Any],
    components: Iterable[Mapping[str, Any]] | None,
) -> dict[str, Any] | None:
    """Return the first supported-script handoff from resolved components."""

    if components is None:
        return None
    for component in components:
        if not isinstance(component, Mapping):
            continue
        match = _classify_component_selector(component)
        if match is not None:
            identity, selector = match
            return _build_script_handoff(source_tool, request, identity, selector)
    return None


def model_facing_script_handoff(
    tool_name: str,
    arguments: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Apply the closed model-facing creation policy without target contact."""

    if tool_name not in MODEL_FACING_COMPONENT_CREATION_ROUTES:
        return None
    request = dict(arguments or {})

    if tool_name == "gh_edit":
        create = request.get("create")
        components = create if isinstance(create, list) else []
    elif tool_name == "gh_explore_component":
        if request.get("instanceGuid"):
            return None
        components = [{"guid": request.get("guid")}]
    else:
        components = [{"guid": request.get("guid")}]

    return resolved_script_handoff(tool_name, request, components)
