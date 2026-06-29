from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE_SCRIPT = (
    REPO_ROOT
    / "experiments"
    / "relationship_fact_projection_smoke"
    / "scripts"
    / "create_smoke_fixture_rhino.py"
)
SMOKE_README = REPO_ROOT / "experiments" / "relationship_fact_projection_smoke" / "README.md"


def test_smoke_fixture_clears_dedicated_layer_before_creating_objects():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")

    assert "def _clear_smoke_layer(layer_index: int) -> int:" in source
    assert '"clearedObjectCount": cleared_count' in source
    assert source.index("_clear_smoke_layer(layer_index)") < source.index("member_curve =")


def test_smoke_fixture_readme_documents_repeatable_layer_clear():
    readme = SMOKE_README.read_text(encoding="utf-8")

    assert "clears the dedicated" in readme
    assert "`Rook_RelationshipFactSmoke` layer" in readme
