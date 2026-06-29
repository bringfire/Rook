# Profile Boundary Audit v1 Design

> Branch/worktree: `codex/profile-boundary-audit-v1` at
> `C:/Users/aryan/source/repos/Rook/.worktrees/pearson-robot-feature-graph`.
>
> This branch is stacked on the frozen `codex/relationship-profile-v1` slice. Do not add more
> commits to `codex/relationship-profile-v1` unless review feedback requires it.

## 1. Context

The recent scenegraph semantics work introduced three distinct layers:

- `scene_semantic_relationships`: raw structured projected relationship fact inspection;
- `scene_object_semantic_context`: selected-object card presentation over those facts;
- relationship profiles: data-defined labels, inverse labels, categories, and contact-kind display
  hints.

The card layer is still useful. Its responsibilities are generic presentation mechanics:

- selected object orientation;
- fact grouping;
- truncation and sample selection;
- count semantics;
- stable raw fact preservation;
- additive profile-enriched labels/categories.

The risk is vocabulary drift. If the card layer starts hard-coding relationship meanings such as
support, hosting, architecture, robot joints, or fixture-specific graph sources, then the profile
boundary becomes cosmetic rather than architectural.

This slice audits and lightly enforces that boundary before geometry evidence or ontology-adjacent
work begins.

## 2. Goal

Add a small Profile Boundary Audit v1:

```text
production semantic-card code
-> owns generic presentation mechanics only
relationship profile / fixtures / tests / docs
-> own domain vocabulary and examples
```

The concrete deliverable is a narrow automated guard plus a documented audit result.

## 3. Non-Goals

This slice does not:

- change card behavior;
- change profile resolution or merge behavior;
- change projection or semantic inspector behavior;
- add ontology predicates, IFC/BOT/Brick/RDF mappings, or geometry evidence rules;
- scan all production code for domain vocabulary;
- scan specs, tests, fixtures, experiments, or profile JSON files;
- refactor the card module unless the guard exposes a real leak.

## 4. Scope

Guard exactly one production file:

```text
mcp_server/src/rook/scene/object_semantic_context.py
```

This is intentionally narrow. The profile boundary being tested here is the card presentation layer,
not the resolver, projection, inspector, default profile, or fixtures.

## 5. Allowed Vocabulary

`object_semantic_context.py` may contain generic presentation and contract language, including:

```text
connected by
relates to
relationship
direction
status
provenance
category
profile
```

These terms describe card mechanics or generic fallback wording. They do not encode a specific
architecture, robot, or fixture ontology.

## 6. Disallowed Domain Vocabulary

The guard should fail if `object_semantic_context.py` hard-codes the following known domain terms in
string literals or comments:

```text
connects
supports
hosted_by
voids
penetrates
bounded_by
column
slab
wall
door
opening
duct
member
joint
architectural_relationship_fixture
pearson_robot_skeleton_graph
```

These terms are valid in:

- `mcp_server/src/rook/scene/default_relationship_profile.json`;
- tests;
- fixture helpers;
- generated experiment assets;
- specs and plans;
- authored graph JSON files.

They are not valid as hard-coded card-layer presentation behavior.

`space` is intentionally excluded from the v1 guard even though it appears as an architectural
object kind in fixtures. It is too generic for a narrow string/comment guard because phrases such as
empty space, whitespace, and namespace are plausible non-domain card comments or strings. Architecture
object-kind ownership for `space` remains covered by the default profile, fixtures, tests, and docs.

## 7. Guard Method

Use Python `tokenize`, not raw substring scanning.

The guard should inspect only:

- `tokenize.STRING`;
- `tokenize.COMMENT`.

This catches hard-coded user-facing strings and comments that normalize domain-specific vocabulary
inside card code, while avoiding false positives in identifiers, imports, type names, or unrelated
syntax.

Suggested helper shape:

```python
def _string_and_comment_text(path: Path) -> list[str]:
    with path.open("rb") as fh:
        tokens = tokenize.tokenize(fh.readline)
        return [
            tok.string
            for tok in tokens
            if tok.type in {tokenize.STRING, tokenize.COMMENT}
        ]
```

The test should report which forbidden term was found and include enough token text to make the
failure actionable.

## 8. Expected Audit Result

At the time of this spec, the production card module appears to use profile-driven labels and
generic fallbacks:

```text
relationshipLabel or relationship or "relates to"
inverseRelationship or "connected by"
contactKindLabel or contactKind
```

That is acceptable because:

- profile labels/inverses override generic fallback wording;
- raw relationship/contact fields are preserved;
- categories come from profile lookup, not card vocabulary tables;
- domain examples live in tests, fixtures, docs, and the default profile.

If the guard passes without production changes, that is a valid completion state.

## 9. Test Plan

Add one focused test module or append to an existing card test module. The preferred file is:

```text
mcp_server/tests/test_object_semantic_context_profile_boundary.py
```

Required tests:

1. Tokenized guard passes for the current `object_semantic_context.py`.
2. A small synthetic token stream or temporary file proves the guard catches a forbidden string
   literal.
3. A small synthetic token stream or temporary file proves the guard catches a forbidden comment.
4. A small synthetic token stream or temporary file proves the guard does not fail on a forbidden
   term used only as an identifier.

The implementation should keep helper code local to the test module unless a broader guard utility
is clearly needed later.

## 10. Review Checklist

Before considering the slice complete:

- `object_semantic_context.py` contains no domain-specific relationship/object/fixture terms in
  string literals or comments;
- guard tests use `tokenize` and inspect only strings/comments;
- no specs/tests/fixtures/default profile files are incorrectly constrained;
- no production behavior changes were made unless required by a guard failure;
- focused tests pass;
- `git diff --check` and `git show --check --stat HEAD` pass.

## 11. Success Criteria

This slice is complete when:

- the profile/card boundary is documented;
- the tokenized guard test is committed;
- the guard is narrow to `object_semantic_context.py`;
- domain vocabulary remains data/test/fixture/doc owned;
- no geometry evidence, ontology, projection, or inspector scope has been added.
