import copy
import re


GH_EDIT_TEMP_ID_PATTERN = r"^T[A-Za-z0-9_]{1,63}$"
_TEMP_ID = re.compile(r"T[A-Za-z0-9_]{1,63}")
_COMPONENT_ID = re.compile(r"C[1-9][0-9]*")
_PORT_INDEX = re.compile(r"[+-]?[0-9]+")

MUTATION_COUNT_KEYS = (
    "created",
    "deleted",
    "values_set",
    "connected",
    "disconnected",
    "groups_created",
    "groups_deleted",
    "groups_updated",
    "grouped",
    "ungrouped",
)


def _parse_flow_ids(flow):
    if not isinstance(flow, str):
        return None
    parts = flow.split(">")
    if len(parts) != 2:
        return None
    source = parts[0].split(".")
    target = parts[1].split(".")
    if len(source) != 2 or len(target) != 2:
        return None

    source_ref = source[1]
    target_ref = target[1]
    if len(source_ref) < 2 or source_ref[0] not in "Oo":
        return None
    if len(target_ref) < 2 or target_ref[0] not in "Ii":
        return None

    source_index = source_ref[1:].strip()
    target_index = target_ref[1:].strip()
    if not _PORT_INDEX.fullmatch(source_index) or not _PORT_INDEX.fullmatch(target_index):
        return None
    source_number = int(source_index)
    target_number = int(target_index)
    if not (0 <= source_number <= 2_147_483_647):
        return None
    if not (0 <= target_number <= 2_147_483_647):
        return None
    return source[0], target[0]


def _issue(path, code, value):
    return {"path": path, "code": code, "value": copy.deepcopy(value)}


def _reference_issue(path, value, declared):
    if isinstance(value, str) and _TEMP_ID.fullmatch(value):
        if value in declared:
            return None
        return _issue(path, "unresolved_temp_reference", value)
    if isinstance(value, str) and _COMPONENT_ID.fullmatch(value):
        return None
    return _issue(path, "invalid_component_reference", value)


def admit_gh_edit_request(arguments):
    """Return one closed pre-dispatch refusal or None without mutating arguments."""
    issues = []
    declared = set()

    create = arguments.get("create", []) if isinstance(arguments, dict) else []
    if not isinstance(create, list):
        issues.append(_issue("/create", "invalid_temp_id", create))
        create = []
    for index, item in enumerate(create):
        value = item.get("temp_id") if isinstance(item, dict) else None
        path = f"/create/{index}/temp_id"
        if not isinstance(value, str) or not _TEMP_ID.fullmatch(value):
            issues.append(_issue(path, "invalid_temp_id", value))
            continue
        if value in declared:
            issues.append(_issue(path, "duplicate_temp_id", value))
            continue
        declared.add(value)

    def scan_flows(field):
        values = arguments.get(field, []) if isinstance(arguments, dict) else []
        if not isinstance(values, list):
            issues.append(_issue(f"/{field}", "invalid_flow", values))
            return
        for index, flow in enumerate(values):
            path = f"/{field}/{index}"
            endpoints = _parse_flow_ids(flow)
            if endpoints is None:
                issues.append(_issue(path, "invalid_flow", flow))
                continue
            for component_id in endpoints:
                issue = _reference_issue(path, component_id, declared)
                if issue is not None:
                    issues.append(issue)

    scan_flows("disconnect")

    set_values = arguments.get("set_values", []) if isinstance(arguments, dict) else []
    if not isinstance(set_values, list):
        issues.append(_issue("/set_values", "invalid_component_reference", set_values))
    else:
        for index, item in enumerate(set_values):
            value = item.get("id") if isinstance(item, dict) else None
            issue = _reference_issue(f"/set_values/{index}/id", value, declared)
            if issue is not None:
                issues.append(issue)

    scan_flows("connect")

    groups = arguments.get("groups", []) if isinstance(arguments, dict) else []
    if not isinstance(groups, list):
        issues.append(_issue("/groups", "invalid_component_reference", groups))
    else:
        for group_index, group in enumerate(groups):
            if not isinstance(group, dict) or "members" not in group:
                continue
            members = group["members"]
            if not isinstance(members, list):
                issues.append(_issue(
                    f"/groups/{group_index}/members",
                    "invalid_component_reference",
                    members,
                ))
                continue
            for member_index, value in enumerate(members):
                issue = _reference_issue(
                    f"/groups/{group_index}/members/{member_index}",
                    value,
                    declared,
                )
                if issue is not None:
                    issues.append(issue)

    if not issues:
        return None
    return {
        "success": False,
        "data": {
            "error": "gh_edit_admission_failed",
            "issues": issues,
        },
    }


def _merge_unique(*issue_lists):
    issues = []
    seen = set()
    for issue_list in issue_lists:
        for issue in _normalize_issues(issue_list):
            if issue not in seen:
                seen.add(issue)
                issues.append(issue)
    return issues


def _normalize_issues(issue_list):
    if isinstance(issue_list, str):
        return [issue_list]
    if not isinstance(issue_list, (list, tuple)):
        return []
    return [issue for issue in issue_list if isinstance(issue, str)]


def extract_edit_summary(result):
    if not isinstance(result, dict):
        return None
    data = result.get("data")
    if not isinstance(data, dict):
        return None
    edit_summary = data.get("edit_summary")
    if not isinstance(edit_summary, dict):
        return None
    return edit_summary


def extract_edit_errors(result):
    edit_summary = extract_edit_summary(result)
    if edit_summary is None:
        return []
    errors = edit_summary.get("errors")
    return _merge_unique(errors)


def has_mutation_evidence(result):
    edit_summary = extract_edit_summary(result)
    if edit_summary is None:
        return False

    for key in MUTATION_COUNT_KEYS:
        value = edit_summary.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            return True

    for key in ("temp_id_map", "instance_guids"):
        value = edit_summary.get(key)
        if isinstance(value, dict) and len(value) > 0:
            return True

    return edit_summary.get("mutation_applied") is True


def apply_gh_edit_contract(result, strict_partial_success=True):
    edit_errors = extract_edit_errors(result)
    if not edit_errors:
        return result

    data = result.setdefault("data", {})
    mutation_applied = has_mutation_evidence(result)

    result["verified"] = False
    result["errors"] = edit_errors
    data["errors"] = edit_errors
    data["warnings"] = _merge_unique(data.get("warnings", []), edit_errors)
    data["verified"] = False

    if mutation_applied:
        note = "Grasshopper edit partially applied, but one or more edit operations failed."
        result["partial_success"] = True
        data["partial_success"] = True
        if strict_partial_success:
            result["success"] = False
    else:
        note = "Grasshopper edit failed before applying any mutations."
        result["success"] = False
        result.pop("partial_success", None)
        data.pop("partial_success", None)

    result["verification_note"] = note
    data["verification_note"] = note
    return result
