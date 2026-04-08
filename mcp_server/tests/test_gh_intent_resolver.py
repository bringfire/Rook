from types import SimpleNamespace

from rook.learning import dspy_modules


def test_resolver_keeps_selected_components_when_wiring_is_partial(monkeypatch):
    selection_result = SimpleNamespace(
        components_to_create=[
            {"guid": "circle-guid", "x": 0, "y": 0},
            {"guid": "slider-guid", "x": -150, "y": 0, "nickname": "Height"},
            {"guid": "extrude-guid", "x": 150, "y": 0},
        ],
        confidence=0.74,
    )
    wiring_result = SimpleNamespace(
        wiring_plan=[
            {"source_index": 1, "target_index": 2, "target_param": "D"},
        ],
        values_to_set=[{"component_index": 1, "value": 10}],
        confidence=0.31,
    )

    class FakePredict:
        def __init__(self, signature):
            self.signature = signature

        def __call__(self, **kwargs):
            if self.signature is dspy_modules.GHSelectComponentsFast:
                return selection_result
            if self.signature is dspy_modules.GHPlanComponentWiringFast:
                assert kwargs["selected_components"][0]["guid"] == "circle-guid"
                assert kwargs["selected_components"][1]["params"]["outputs"] == {"N": "Number"}
                assert kwargs["selected_components"][2]["params"]["inputs"] == {"B": "Brep", "D": "Vector"}
                return wiring_result
            raise AssertionError(f"Unexpected signature: {self.signature}")

    monkeypatch.setattr(dspy_modules.dspy, "Predict", FakePredict)
    monkeypatch.delenv("ROOK_DSPY_COT", raising=False)

    resolver = dspy_modules.GHIntentResolver()
    result = resolver.forward(
        user_intent="create a circle, extrude it with a height slider",
        candidate_guids=["circle-guid", "slider-guid", "extrude-guid"],
        tiered_knowledge=[
            {
                "guid": "circle-guid",
                "name": "Circle",
                "family": "curve",
                "quick": "Circle | Inputs: P, R -> C",
                "params": {"inputs": {"P": "Plane", "R": "Number"}, "outputs": {"C": "Circle"}},
                "deprecated": False,
            },
            {
                "guid": "slider-guid",
                "name": "Number Slider",
                "family": "params",
                "quick": "Slider",
                "params": {"inputs": {}, "outputs": {"N": "Number"}},
                "deprecated": False,
            },
            {
                "guid": "extrude-guid",
                "name": "Extrude",
                "family": "surface",
                "quick": "Extrude | Inputs: B, D -> E",
                "params": {"inputs": {"B": "Brep", "D": "Vector"}, "outputs": {"E": "Surface"}},
                "deprecated": False,
            },
        ],
        canvas_state=[],
    )

    assert [c["guid"] for c in result.components_to_create] == [
        "circle-guid",
        "slider-guid",
        "extrude-guid",
    ]
    assert result.wiring_plan == wiring_result.wiring_plan
    assert result.values_to_set == wiring_result.values_to_set
    assert result.confidence == 0.74
    assert result.selection_confidence == 0.74
    assert result.wiring_confidence == 0.31
    assert result.rationale == ""


def test_resolver_dedupes_variants_and_restores_explicit_mentions(monkeypatch):
    selection_result = SimpleNamespace(
        components_to_create=[
            {"guid": "slider-guid", "x": -150, "y": 0},
            {"guid": "extrude-guid", "x": 150, "y": 0},
        ],
        confidence=0.72,
    )
    wiring_result = SimpleNamespace(
        wiring_plan=[{"source_index": 1, "target_index": 2, "target_param": "D"}],
        values_to_set=[],
        confidence=0.4,
    )

    class FakePredict:
        def __init__(self, signature):
            self.signature = signature

        def __call__(self, **kwargs):
            if self.signature is dspy_modules.GHSelectComponentsFast:
                assert kwargs["candidate_guids"] == [
                    "circle-guid",
                    "incircle-guid",
                    "extrude-guid",
                    "mesh-extrude-guid",
                    "slider-guid",
                ]
                return selection_result
            if self.signature is dspy_modules.GHPlanComponentWiringFast:
                assert [c["guid"] for c in kwargs["selected_components"]] == [
                    "circle-guid",
                    "extrude-guid",
                    "slider-guid",
                ]
                return wiring_result
            raise AssertionError(f"Unexpected signature: {self.signature}")

    monkeypatch.setattr(dspy_modules.dspy, "Predict", FakePredict)
    monkeypatch.delenv("ROOK_DSPY_COT", raising=False)

    resolver = dspy_modules.GHIntentResolver()
    result = resolver.forward(
        user_intent="create a circle, extrude it with a height slider",
        candidate_guids=[
            "circle-guid",
            "circle-cnr-guid",
            "incircle-guid",
            "extrude-guid",
            "extrude-linear-guid",
            "mesh-extrude-guid",
            "slider-guid",
            "md-slider-guid",
        ],
        tiered_knowledge=[
            {"guid": "circle-guid", "name": "Circle", "family": "curve", "quick": "", "params": {"inputs": {"P": "Plane", "R": "Number"}, "outputs": {"C": "Circle"}}, "deprecated": False},
            {"guid": "circle-cnr-guid", "name": "Circle CNR", "family": "curve", "quick": "", "params": {}, "deprecated": False},
            {"guid": "incircle-guid", "name": "InCircle", "family": "curve", "quick": "", "params": {}, "deprecated": False},
            {"guid": "extrude-guid", "name": "Extrude", "family": "surface", "quick": "", "params": {"inputs": {"B": "Brep", "D": "Vector"}, "outputs": {"E": "Surface"}}, "deprecated": False},
            {"guid": "extrude-linear-guid", "name": "Extrude Linear", "family": "surface", "quick": "", "params": {}, "deprecated": False},
            {"guid": "mesh-extrude-guid", "name": "Mesh Extrude", "family": "mesh", "quick": "", "params": {}, "deprecated": False},
            {"guid": "slider-guid", "name": "Number Slider", "family": "params", "quick": "", "params": {"inputs": {}, "outputs": {"N": "Number"}}, "deprecated": False},
            {"guid": "md-slider-guid", "name": "MD Slider", "family": "params", "quick": "", "params": {}, "deprecated": False},
        ],
        canvas_state=[],
    )

    assert [c["guid"] for c in result.components_to_create] == [
        "circle-guid",
        "extrude-guid",
        "slider-guid",
    ]


def test_generic_slider_prefers_number_slider(monkeypatch):
    selection_result = SimpleNamespace(
        components_to_create=[
            {"guid": "md-slider-guid", "x": -150, "y": 0},
            {"guid": "sphere-guid", "x": 150, "y": 0},
        ],
        confidence=0.95,
    )
    wiring_result = SimpleNamespace(
        wiring_plan=[{"source_index": 0, "target_index": 1, "target_param": "R"}],
        values_to_set=[],
        confidence=0.88,
    )

    class FakePredict:
        def __init__(self, signature):
            self.signature = signature

        def __call__(self, **kwargs):
            if self.signature is dspy_modules.GHSelectComponentsFast:
                assert kwargs["candidate_guids"] == ["slider-guid", "sphere-guid"]
                return selection_result
            if self.signature is dspy_modules.GHPlanComponentWiringFast:
                assert [c["guid"] for c in kwargs["selected_components"]] == [
                    "slider-guid",
                    "sphere-guid",
                ]
                return wiring_result
            raise AssertionError(f"Unexpected signature: {self.signature}")

    monkeypatch.setattr(dspy_modules.dspy, "Predict", FakePredict)
    monkeypatch.delenv("ROOK_DSPY_COT", raising=False)

    resolver = dspy_modules.GHIntentResolver()
    result = resolver.forward(
        user_intent="create a sphere with a radius slider",
        candidate_guids=["md-slider-guid", "slider-guid", "sphere-guid"],
        tiered_knowledge=[
            {"guid": "md-slider-guid", "name": "MD Slider", "family": "params", "quick": "", "params": {"inputs": {}, "outputs": {"N": "Number"}}, "deprecated": False},
            {"guid": "slider-guid", "name": "Number Slider", "family": "params", "quick": "", "params": {"inputs": {}, "outputs": {"N": "Number"}}, "deprecated": False},
            {"guid": "sphere-guid", "name": "Sphere", "family": "surface", "quick": "", "params": {"inputs": {"R": "Number"}, "outputs": {"S": "Sphere"}}, "deprecated": False},
        ],
        canvas_state=[],
    )

    assert [c["guid"] for c in result.components_to_create] == [
        "slider-guid",
        "sphere-guid",
    ]


def test_explicit_md_slider_preserves_md_slider(monkeypatch):
    selection_result = SimpleNamespace(
        components_to_create=[{"guid": "slider-guid", "x": 0, "y": 0}],
        confidence=0.91,
    )
    wiring_result = SimpleNamespace(
        wiring_plan=[],
        values_to_set=[],
        confidence=0.91,
    )

    class FakePredict:
        def __init__(self, signature):
            self.signature = signature

        def __call__(self, **kwargs):
            if self.signature is dspy_modules.GHSelectComponentsFast:
                assert kwargs["candidate_guids"] == ["md-slider-guid"]
                return selection_result
            if self.signature is dspy_modules.GHPlanComponentWiringFast:
                assert [c["guid"] for c in kwargs["selected_components"]] == ["md-slider-guid"]
                return wiring_result
            raise AssertionError(f"Unexpected signature: {self.signature}")

    monkeypatch.setattr(dspy_modules.dspy, "Predict", FakePredict)
    monkeypatch.delenv("ROOK_DSPY_COT", raising=False)

    resolver = dspy_modules.GHIntentResolver()
    result = resolver.forward(
        user_intent="create an MD slider",
        candidate_guids=["md-slider-guid", "slider-guid"],
        tiered_knowledge=[
            {"guid": "md-slider-guid", "name": "MD Slider", "family": "params", "quick": "", "params": {"inputs": {}, "outputs": {"N": "Number"}}, "deprecated": False},
            {"guid": "slider-guid", "name": "Number Slider", "family": "params", "quick": "", "params": {"inputs": {}, "outputs": {"N": "Number"}}, "deprecated": False},
        ],
        canvas_state=[],
    )

    assert [c["guid"] for c in result.components_to_create] == ["md-slider-guid"]


def test_resolver_combines_cot_rationales(monkeypatch):
    selection_result = SimpleNamespace(
        components_to_create=[{"guid": "sphere-guid", "x": 0, "y": 0}],
        confidence="0.83",
        rationale="Sphere is explicitly requested.",
    )
    wiring_result = SimpleNamespace(
        wiring_plan=[],
        values_to_set=[],
        confidence="0.55",
        rationale="No wiring is needed for a single component.",
    )

    class FakeChainOfThought:
        def __init__(self, signature):
            self.signature = signature

        def __call__(self, **kwargs):
            if self.signature is dspy_modules.GHSelectComponents:
                return selection_result
            if self.signature is dspy_modules.GHPlanComponentWiring:
                return wiring_result
            raise AssertionError(f"Unexpected signature: {self.signature}")

    monkeypatch.setattr(dspy_modules.dspy, "ChainOfThought", FakeChainOfThought)
    monkeypatch.setenv("ROOK_DSPY_COT", "1")

    resolver = dspy_modules.GHIntentResolver()
    result = resolver.forward(
        user_intent="create a sphere",
        candidate_guids=["sphere-guid"],
        tiered_knowledge=[
            {
                "guid": "sphere-guid",
                "name": "Sphere",
                "family": "surface",
                "quick": "Sphere",
                "params": {"inputs": {"R": "Number"}, "outputs": {"S": "Sphere"}},
                "deprecated": False,
            }
        ],
        canvas_state=[],
    )

    assert result.components_to_create == [{"guid": "sphere-guid", "x": 0, "y": 0}]
    assert result.confidence == 0.83
    assert result.selection_confidence == 0.83
    assert result.wiring_confidence == 0.55
    assert result.rationale == (
        "Selection: Sphere is explicitly requested.\n"
        "Wiring: No wiring is needed for a single component."
    )
