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
