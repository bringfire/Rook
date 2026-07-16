from __future__ import annotations

import hashlib
import importlib
import json
from dataclasses import FrozenInstanceError, replace
from types import MappingProxyType, SimpleNamespace

import pytest


try:
    lifecycle = importlib.import_module("rook.tool_lifecycle")
except ModuleNotFoundError as exc:
    if exc.name != "rook.tool_lifecycle":
        raise
    lifecycle = None
    _IMPORT_ERROR = True
else:
    _IMPORT_ERROR = False


def test_lifecycle_contract_is_available() -> None:
    assert not _IMPORT_ERROR, (
        "EXPECTED_RED:T1:LIFECYCLE rook.tool_lifecycle is not implemented"
    )


if lifecycle is not None:
    LifecycleDisposition = lifecycle.LifecycleDisposition
    DispatchOrigin = lifecycle.DispatchOrigin
    LifecycleEntry = lifecycle.LifecycleEntry

    EXPECTED = {
        "gh_execute_intent": {
            "disposition": "retired",
            "recovery": (
                "Rediscover the current Grasshopper surface; inspect state and "
                "components, then use explicit gh_edit or supported script tools "
                "and verify solve state, outputs, and errors."
            ),
            "restoration_criteria": (),
        },
        "rhino_execute_intent": {
            "disposition": "retired",
            "recovery": (
                "Rediscover the current Rhino surface; use explicit typed Rhino "
                "tools, rhino_execute, or a sanctioned preflighted rhino_command, "
                "then verify the host result."
            ),
            "restoration_criteria": (),
        },
        "plan_and_execute": {
            "disposition": "suspended",
            "recovery": (
                "Rediscover the current surface and perform bounded steps through "
                "explicit admitted tools; autonomous plan execution is suspended."
            ),
            "restoration_criteria": (
                "A bounded plan contract limits admitted node identities, call "
                "counts, targets, and mutation scope.",
                "Every live node re-enters lifecycle and profile guards before "
                "parameters are copied or execution begins.",
                "Readiness, host verification, failure, and restoration evidence "
                "are deterministic and independently reviewed.",
            ),
        },
        "spawn_agent": {
            "disposition": "suspended",
            "recovery": (
                "Rediscover the current surface and use the connected model to call "
                "explicit admitted tools directly; autonomous agent spawning is "
                "suspended."
            ),
            "restoration_criteria": (
                "Agent authority is bounded by admitted tool identities, explicit "
                "targets, deterministic call budgets, and stop conditions.",
                "Injected and local registries are filtered and every invocation "
                "independently re-enters lifecycle and profile guards.",
                "Live readiness, verification, restoration, and runaway-control "
                "evidence is recorded and independently approved.",
            ),
        },
        "gh_explore_workflow": {
            "disposition": "suspended",
            "recovery": (
                "Rediscover the current Grasshopper inspection surface and use "
                "explicit snapshot, component, or knowledge tools; semantic "
                "workflow exploration is suspended."
            ),
            "restoration_criteria": (
                "The contract is proven host-read-only or every possible mutation "
                "is explicit, bounded, authorized, and verified.",
                "Knowledge or model output cannot directly carry mutation authority "
                "into a hidden executor.",
                "Deterministic tests and live evidence prove the bounded contract "
                "and absence of undeclared host mutation.",
            ),
        },
        "gh_replay_recipe": {
            "disposition": "suspended",
            "recovery": (
                "Rediscover the current Grasshopper surface and apply reviewed "
                "explicit gh_edit operations; recipe replay is suspended."
            ),
            "restoration_criteria": (
                "Recipes use a versioned bounded schema containing only explicit "
                "admitted operations and validated arguments.",
                "Preflight establishes target ownership, readiness, mutation bounds, "
                "and a restoration plan before execution.",
                "Execution produces deterministic host verification and verified "
                "restoration or an approved durable recovery receipt.",
            ),
        },
    }
    EXPECTED_NAMES = frozenset(EXPECTED)

    def _entry(
        *,
        name: str = "safe_tool",
        disposition: LifecycleDisposition = LifecycleDisposition.SUSPENDED,
        recovery: str = "Use an admitted explicit tool.",
        restoration_criteria: tuple[str, ...] = ("Independent review is complete.",),
        aliases: tuple[str, ...] = (),
    ) -> LifecycleEntry:
        return LifecycleEntry(
            name=name,
            disposition=disposition,
            recovery=recovery,
            restoration_criteria=restoration_criteria,
            aliases=aliases,
        )

    def _build(*entries: LifecycleEntry):
        return lifecycle._build_manifest(tuple(entries))

    def _schema(name: object) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": "test schema",
                "parameters": {"type": "object", "properties": {}},
            },
        }

    def test_enums_have_the_closed_values() -> None:
        assert {item.value for item in LifecycleDisposition} == {
            "retired",
            "suspended",
        }
        assert {item.value for item in DispatchOrigin} == {
            "public_mcp",
            "progressive_meta",
            "server_dispatch",
            "rook_agent",
            "rook_chat",
            "plan_graph",
            "tool_dispatcher",
            "internal_handler",
        }

    def test_manifest_pins_all_six_entries_exactly() -> None:
        manifest = lifecycle.lifecycle_manifest()
        assert frozenset(manifest) == EXPECTED_NAMES
        assert lifecycle.contained_names() == EXPECTED_NAMES
        assert isinstance(lifecycle.contained_names(), frozenset)

        for name, expected in EXPECTED.items():
            entry = manifest[name]
            assert entry.name == name
            assert entry.disposition.value == expected["disposition"]
            assert entry.recovery == expected["recovery"]
            assert entry.restoration_criteria == expected["restoration_criteria"]
            assert entry.aliases == ()
            assert isinstance(entry.restoration_criteria, tuple)
            assert isinstance(entry.aliases, tuple)

    def test_manifest_and_entries_are_immutable() -> None:
        manifest = lifecycle.lifecycle_manifest()
        assert isinstance(manifest, type(MappingProxyType({})))
        assert isinstance(lifecycle._IDENTITY_INDEX, type(MappingProxyType({})))
        with pytest.raises(TypeError):
            manifest["new_tool"] = _entry(name="new_tool")
        with pytest.raises(FrozenInstanceError):
            manifest["spawn_agent"].name = "other"

    @pytest.mark.parametrize(
        "raw",
        [
            None,
            1,
            b"gh_execute_intent",
            " GH_EXECUTE_INTENT",
            "gh_execute_intent ",
            "GH_EXECUTE_INTENT",
            "gh_execute",
        ],
    )
    def test_resolver_never_coerces_or_normalizes(raw: object) -> None:
        assert lifecycle.resolve_contained_identity(raw) is None

    @pytest.mark.parametrize("name", sorted(EXPECTED_NAMES))
    def test_exact_identity_resolves(name: str) -> None:
        assert lifecycle.resolve_contained_identity(name).name == name

    def test_resolver_does_not_call_string_conversion() -> None:
        class LooksContained:
            def __str__(self) -> str:
                raise AssertionError("resolver must not coerce")

        assert lifecycle.resolve_contained_identity(LooksContained()) is None

    @pytest.mark.parametrize(
        "name",
        [
            "a",
            "a0",
            "a_b",
            "a" + ("0" * 127),
        ],
    )
    def test_name_grammar_accepts_valid_ascii_boundaries(name: str) -> None:
        manifest, identities = _build(_entry(name=name))
        assert manifest[name].name == name
        assert identities[name].name == name

    @pytest.mark.parametrize(
        "name",
        [
            "",
            "_tool",
            "1tool",
            "Tool",
            "tool-name",
            "tool.name",
            "tool name",
            "a" * 129,
            "tøol",
        ],
    )
    def test_name_grammar_ascii_and_128_byte_limit_reject_invalid(name: str) -> None:
        with pytest.raises(ValueError):
            _build(_entry(name=name))

    def test_alias_limit_accepts_16_and_sorts_only_for_canonical_json() -> None:
        aliases = tuple(f"alias_{index:02d}" for index in reversed(range(16)))
        entry = _entry(aliases=aliases)
        manifest, identities = _build(entry)
        assert manifest[entry.name].aliases == aliases
        assert all(identities[alias] is manifest[entry.name] for alias in aliases)

        canonical = json.loads(lifecycle._canonical_manifest_json(manifest))
        assert canonical[0]["aliases"] == sorted(aliases)

    def test_alias_limit_rejects_17() -> None:
        aliases = tuple(f"alias_{index:02d}" for index in range(17))
        with pytest.raises(ValueError):
            _build(_entry(aliases=aliases))

    @pytest.mark.parametrize("recovery", ["x", "é" * 256])
    def test_recovery_accepts_1_to_512_utf8_bytes(recovery: str) -> None:
        assert 1 <= len(recovery.encode("utf-8")) <= 512
        manifest, _ = _build(_entry(recovery=recovery))
        assert manifest["safe_tool"].recovery == recovery

    @pytest.mark.parametrize("recovery", ["", ("é" * 256) + "a"])
    def test_recovery_rejects_outside_1_to_512_utf8_bytes(recovery: str) -> None:
        with pytest.raises(ValueError):
            _build(_entry(recovery=recovery))

    @pytest.mark.parametrize(
        "control",
        ["\n", "\r", "\t", "\x00", "\x1f", "\x7f", "\u0085", "\u2028"],
    )
    def test_recovery_rejects_line_breaks_and_unicode_controls(control: str) -> None:
        with pytest.raises(ValueError):
            _build(_entry(recovery=f"before{control}after"))

    @pytest.mark.parametrize("count", [1, 16])
    def test_suspended_criteria_accepts_1_to_16_items(count: int) -> None:
        criteria = tuple(f"Criterion {index}." for index in range(count))
        manifest, _ = _build(_entry(restoration_criteria=criteria))
        assert manifest["safe_tool"].restoration_criteria == criteria

    @pytest.mark.parametrize("count", [0, 17])
    def test_suspended_criteria_rejects_outside_1_to_16_items(count: int) -> None:
        criteria = tuple(f"Criterion {index}." for index in range(count))
        with pytest.raises(ValueError):
            _build(_entry(restoration_criteria=criteria))

    @pytest.mark.parametrize("criterion", ["x", "é" * 128])
    def test_criterion_accepts_1_to_256_utf8_bytes(criterion: str) -> None:
        manifest, _ = _build(_entry(restoration_criteria=(criterion,)))
        assert manifest["safe_tool"].restoration_criteria == (criterion,)

    @pytest.mark.parametrize("criterion", ["", ("é" * 128) + "a"])
    def test_criterion_rejects_outside_1_to_256_utf8_bytes(
        criterion: str,
    ) -> None:
        with pytest.raises(ValueError):
            _build(_entry(restoration_criteria=(criterion,)))

    @pytest.mark.parametrize(
        "control",
        ["\n", "\r", "\t", "\x00", "\x1f", "\x7f", "\u0085", "\u2028"],
    )
    def test_criteria_independently_reject_every_line_or_control_class(
        control: str,
    ) -> None:
        criterion = f"before{control}after"
        assert len(criterion.encode("utf-8")) < 256
        with pytest.raises(ValueError):
            _build(_entry(restoration_criteria=(criterion,)))

    def test_retired_requires_empty_restoration_criteria() -> None:
        retired = _entry(
            disposition=LifecycleDisposition.RETIRED,
            restoration_criteria=(),
        )
        manifest, _ = _build(retired)
        assert manifest["safe_tool"].restoration_criteria == ()

        with pytest.raises(ValueError):
            _build(
                replace(
                    retired,
                    restoration_criteria=("This must remain empty.",),
                )
            )

    @pytest.mark.parametrize(
        "entries",
        [
            (
                _entry(name="first_tool"),
                _entry(name="first_tool"),
            ),
            (
                _entry(name="first_tool", aliases=("second_tool",)),
                _entry(name="second_tool"),
            ),
            (
                _entry(name="first_tool", aliases=("shared_alias",)),
                _entry(name="second_tool", aliases=("shared_alias",)),
            ),
            (
                _entry(name="first_tool", aliases=("first_tool",)),
            ),
        ],
    )
    def test_identity_collisions_are_rejected(
        entries: tuple[LifecycleEntry, ...],
    ) -> None:
        with pytest.raises(ValueError):
            _build(*entries)

    def test_tuple_fields_are_required_for_immutable_entries() -> None:
        with pytest.raises(ValueError):
            _build(
                LifecycleEntry(
                    name="safe_tool",
                    disposition=LifecycleDisposition.SUSPENDED,
                    recovery="Use an admitted explicit tool.",
                    restoration_criteria=["Independent review is complete."],
                    aliases=(),
                )
            )
        with pytest.raises(ValueError):
            _build(
                LifecycleEntry(
                    name="safe_tool",
                    disposition=LifecycleDisposition.SUSPENDED,
                    recovery="Use an admitted explicit tool.",
                    restoration_criteria=("Independent review is complete.",),
                    aliases=["safe_alias"],
                )
            )

    def test_canonical_json_and_sha256_are_fully_pinned() -> None:
        expected_records = [
            {
                "name": name,
                "disposition": data["disposition"],
                "recovery": data["recovery"],
                "restoration_criteria": list(data["restoration_criteria"]),
                "aliases": [],
            }
            for name, data in sorted(EXPECTED.items())
        ]
        expected_json = json.dumps(
            expected_records,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        actual = lifecycle.canonical_manifest_json()

        assert actual == expected_json
        assert [record["name"] for record in json.loads(actual)] == sorted(
            EXPECTED_NAMES
        )
        assert lifecycle.lifecycle_fingerprint() == hashlib.sha256(
            expected_json.encode("utf-8")
        ).hexdigest()

    def test_canonical_json_sorts_aliases_but_preserves_criteria_order() -> None:
        entry = _entry(
            aliases=("z_alias", "a_alias"),
            restoration_criteria=("Second by wording.", "First by wording."),
        )
        manifest, _ = _build(entry)
        record = json.loads(lifecycle._canonical_manifest_json(manifest))[0]
        assert record["aliases"] == ["a_alias", "z_alias"]
        assert record["restoration_criteria"] == [
            "Second by wording.",
            "First by wording.",
        ]
        assert lifecycle._canonical_manifest_json(manifest).startswith(
            '[{"aliases":'
        )

    @pytest.mark.parametrize("name", sorted(EXPECTED_NAMES))
    def test_denial_payload_and_internal_envelope_are_exact(name: str) -> None:
        entry = lifecycle.resolve_contained_identity(name)
        expected_payload = {
            "code": "legacy_semantic_tool_contained",
            "tool": name,
            "disposition": EXPECTED[name]["disposition"],
            "retryable": False,
            "verified": False,
            "recovery": EXPECTED[name]["recovery"],
        }
        payload = lifecycle.containment_payload(entry)
        envelope = lifecycle.containment_envelope(entry)

        assert payload == expected_payload
        assert envelope == {"success": False, "data": expected_payload}
        assert "restoration_criteria" not in payload
        assert "aliases" not in payload
        assert "restoration_criteria" not in envelope["data"]
        assert "aliases" not in envelope["data"]

    def test_mcp_projection_checks_raw_record_name() -> None:
        safe = SimpleNamespace(name="safe")
        contained = SimpleNamespace(name="spawn_agent")
        mapping_safe = {"name": "mapping_safe", "other": 1}
        mapping_contained = {"name": "plan_and_execute", "other": 2}
        malformed = object()

        assert lifecycle.filter_mcp_records(
            [safe, contained, mapping_safe, mapping_contained, malformed]
        ) == [safe, mapping_safe, malformed]

    def test_mapping_projection_checks_raw_key_and_embedded_name() -> None:
        records = {
            "safe_key": _schema("gh_execute_intent"),
            "rhino_execute_intent": _schema("safe_embedded"),
            "safe": _schema("safe"),
        }
        assert lifecycle.filter_litellm_catalog(records) == {
            "safe": _schema("safe")
        }

    def test_mapping_projection_is_noncoercing_and_preserves_malformed_records() -> None:
        class LooksContained:
            def __str__(self) -> str:
                raise AssertionError("projection must not coerce")

        key = LooksContained()
        malformed = object()
        records = {
            key: _schema(LooksContained()),
            "plain": malformed,
            "mismatch": _schema("different_safe_name"),
        }
        assert lifecycle.filter_litellm_catalog(records) == records

    def test_litellm_schema_projection_checks_embedded_raw_name() -> None:
        safe = _schema("safe")
        contained = _schema("gh_replay_recipe")
        malformed = {"function": "not-a-mapping"}
        malformed_object = object()
        assert lifecycle.filter_litellm_schemas(
            [safe, contained, malformed, malformed_object]
        ) == [safe, malformed, malformed_object]

    def test_litellm_schema_projection_preserves_object_identity() -> None:
        safe = _schema("safe")
        malformed = object()
        projected = lifecycle.filter_litellm_schemas(
            [safe, _schema("gh_replay_recipe"), malformed]
        )
        assert projected == [safe, malformed]
        assert projected[0] is safe
        assert projected[1] is malformed

    def test_local_registration_projection_checks_only_raw_key() -> None:
        registrations = {
            "safe": "keep",
            "spawn_agent": "drop",
            1: "keep-non-string",
        }
        assert lifecycle.filter_local_registrations(registrations) == {
            "safe": "keep",
            1: "keep-non-string",
        }
