from rook.scene.relationship_fact_roundtrip import compare_roundtrip


EXPECTED_FACT = {
    "relationship": "connects",
    "fromFeature": "smoke_member.start",
    "toFeature": "smoke_joint.point",
    "contactKind": "point_to_point",
    "provenance": "authored_assembly_graph",
    "status": "accepted",
    "graphSource": "relationship_fact_smoke",
    "graphRevision": "smoke001",
    "pose": "smoke_pose",
}


REQUIRED_CONTEXT = [
    "connects",
    "connected by",
    "smoke_member.start -> smoke_joint.point",
    "point_to_point",
    "accepted",
    "authored_assembly_graph",
]


CONTEXT_TEXT = """
connects: POINT via smoke_member.start -> smoke_joint.point, point_to_point, accepted, authored_assembly_graph
connected by: CURVE via smoke_member.start -> smoke_joint.point, point_to_point, accepted, authored_assembly_graph
"""


def test_compare_roundtrip_exact_fact_and_context_succeeds():
    report = compare_roundtrip(
        expected_facts=[EXPECTED_FACT],
        actual_facts=[dict(EXPECTED_FACT, fromObjectId="member-id", toObjectId="joint-id")],
        context_text=CONTEXT_TEXT,
        required_substrings=REQUIRED_CONTEXT,
    )

    assert report == {
        "success": True,
        "missingFacts": [],
        "unexpectedFacts": [],
        "wrongMetadata": [],
        "missingContextSubstrings": [],
    }


def test_compare_roundtrip_reports_missing_fact():
    report = compare_roundtrip(
        expected_facts=[EXPECTED_FACT],
        actual_facts=[],
        context_text=CONTEXT_TEXT,
        required_substrings=REQUIRED_CONTEXT,
    )

    assert report["success"] is False
    assert report["missingFacts"] == [EXPECTED_FACT]
    assert report["unexpectedFacts"] == []
    assert report["wrongMetadata"] == []
    assert report["missingContextSubstrings"] == []


def test_compare_roundtrip_reports_unexpected_fact():
    unexpected = dict(EXPECTED_FACT, toFeature="smoke_other.point")

    report = compare_roundtrip(
        expected_facts=[EXPECTED_FACT],
        actual_facts=[unexpected],
        context_text=CONTEXT_TEXT,
        required_substrings=REQUIRED_CONTEXT,
    )

    assert report["success"] is False
    assert report["missingFacts"] == [EXPECTED_FACT]
    assert report["unexpectedFacts"] == [unexpected]
    assert report["wrongMetadata"] == []
    assert report["missingContextSubstrings"] == []


def test_compare_roundtrip_reports_wrong_metadata_for_matching_identity():
    actual = dict(EXPECTED_FACT, status="candidate")

    report = compare_roundtrip(
        expected_facts=[EXPECTED_FACT],
        actual_facts=[actual],
        context_text=CONTEXT_TEXT,
        required_substrings=REQUIRED_CONTEXT,
    )

    assert report["success"] is False
    assert report["missingFacts"] == []
    assert report["unexpectedFacts"] == []
    assert report["wrongMetadata"] == [
        {
            "identity": {
                "relationship": "connects",
                "fromFeature": "smoke_member.start",
                "toFeature": "smoke_joint.point",
                "graphSource": "relationship_fact_smoke",
                "graphRevision": "smoke001",
                "pose": "smoke_pose",
            },
            "expected": {"status": "accepted"},
            "actual": {"status": "candidate"},
        }
    ]
    assert report["missingContextSubstrings"] == []


def test_compare_roundtrip_reports_missing_context_substrings():
    report = compare_roundtrip(
        expected_facts=[EXPECTED_FACT],
        actual_facts=[EXPECTED_FACT],
        context_text="connects: smoke_member.start -> smoke_joint.point",
        required_substrings=REQUIRED_CONTEXT,
    )

    assert report["success"] is False
    assert report["missingFacts"] == []
    assert report["unexpectedFacts"] == []
    assert report["wrongMetadata"] == []
    assert report["missingContextSubstrings"] == [
        "connected by",
        "point_to_point",
        "accepted",
        "authored_assembly_graph",
    ]
