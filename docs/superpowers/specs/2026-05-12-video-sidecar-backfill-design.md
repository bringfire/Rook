# Slice 5 Video Sidecar Backfill Design

Date: 2026-05-12

## Context

RookVision generated-video sidecar production is now in place for newly
completed jobs:

- `poster` is a display-only thumbnail sidecar.
- `start_frame` is decoded primary-video-stream frame index `0`.
- `end_frame` is the final decodable primary-video-stream frame.
- New completed generated videos attempt all three sidecars from the saved
  local MP4 after durable `video` artifact creation.
- Poster and frame sidecars publish through `VideoSidecarPublisher`.
- Derivative failures are best-effort and non-fatal once the durable MP4
  artifact exists.

Older generated-video artifacts can still lack one or more of these roles
because they were created before Slice 3 and Slice 4. Slice 5 adds cautious
opportunistic backfill from the already-local MP4 blobs. It does not repair the
whole artifact store, rerun provider jobs, infer provider payload fields, or
add any new public surface.

## Decision

Add a bounded startup backfill service for existing generated-video artifacts.

The service scans existing artifacts, selects only eligible `generated_video`
artifacts that already have a local `video` blob, computes missing sidecar
roles, and attempts only those missing roles. It is invoked from startup as an
asynchronous best-effort one-shot with a small artifact cap and an elapsed-time
budget check between units of work.

The startup sweep is intentionally conservative:

- run once per plugin process;
- return startup control immediately after scheduling;
- touch at most a small number of eligible artifacts, default `10`;
- check budget before starting each artifact and before starting each role;
- never cancel an in-flight ffmpeg process solely because the sweep budget has
  expired;
- report structured diagnostic results;
- treat all failures as non-fatal diagnostics.

This is not a general artifact repair framework. It is a narrow backfill path
for generated-video sidecars that can be derived from a saved local MP4.

## Architecture

### `VideoSidecarBackfillService`

Add an internal managed service that owns artifact-aware backfill orchestration.

It owns:

- artifact enumeration through `ArtifactStore.List()`;
- generated-video eligibility checks;
- local `video` blob availability checks;
- missing-role planning;
- artifact cap enforcement;
- elapsed budget checks;
- deterministic role attempt ordering;
- aggregation of structured diagnostics.

It does not own:

- ffmpeg command construction;
- frame selector semantics;
- poster timestamp extraction semantics;
- sidecar storage policy;
- provider lifecycle;
- job ledger state;
- startup scheduling.

Eligible artifacts must satisfy all of:

- `artifact.Kind == "generated_video"`;
- manifest includes role `video`;
- `ArtifactStore.GetBlobAbsolutePath(artifact.Id, VideoMediaRoles.Video)`
  succeeds for the `video` blob.

The service must skip:

- non-video artifacts;
- generated-video artifacts without a `video` role;
- generated-video artifacts whose `video` blob is missing or unreadable;
- artifacts that already have all target sidecar roles.

Target sidecar roles are:

1. `poster`
2. `start_frame`
3. `end_frame`

The role order is deterministic to keep tests and manifest evolution stable.

### `VideoPosterSidecarProducer`

Keep the poster producer poster-shaped and timestamp/display-oriented.

The backfill service calls `TryPublishPosterAsync(...)` only when the artifact
is missing `poster`. If both frame roles exist but `poster` is missing, the
service runs only the poster path.

No new timestamp selector or frame-source semantics are introduced.

### `VideoFrameSidecarProducer`

Add a narrow internal role-targeted frame sidecar producer path for backfill.

The existing new-video path can continue to request both frame sidecars:

```csharp
Task<VideoFrameSidecarResult> TryPublishFrameSidecarsAsync(
    Guid artifactId,
    CancellationToken cancellationToken);
```

The backfill path should be able to request only the missing frame roles:

```csharp
Task<VideoFrameSidecarResult> TryPublishFrameSidecarsAsync(
    Guid artifactId,
    IReadOnlyList<string> roles,
    CancellationToken cancellationToken);
```

This overload is internal. It is not a public API, route, MCP surface, GH NLE
surface, or provider contract.

Slice 5 callers use the overload with one frame role per call. That preserves
the backfill service's ability to check elapsed budget between `start_frame`
and `end_frame` extraction. The overload accepts a role list to keep the
producer shape reusable, but the startup backfill service must not hide multiple
role attempts behind one call when it needs per-role budget checks.

Role validation must happen before resolving the local video blob, creating temp
paths, or resolving `ffmpeg.exe`. If the requested role list contains only
unknown frame roles, the producer returns diagnostic per-role failures without
doing filesystem or ffmpeg work.

Known role mapping remains:

- `start_frame` -> `VideoFrameSelector.First`
- `end_frame` -> `VideoFrameSelector.Last`

Unknown roles are diagnostic failures. They must not fall back to timestamp
behavior, whole-artifact inference, poster semantics, or provider payload
fields.

If only `end_frame` is missing, the backfill service must request only
`end_frame`. It must not call the two-role producer and rely on duplicate-skip
publication to bound the work.

### Startup Composition

Keep backfill separate from existing job reconciliation.

`RookSubsystemRoot.ReconcileVideoJobsOnce()` remains ledger/job-state
reconciliation only. Slice 5 adds a separate one-shot guard, for example:

```csharp
RookSubsystemRoot.Instance.BackfillVideoSidecarsOnce();
```

The one-shot guard is per process/root and is independent of the job reconcile
guard. It marks itself fired once scheduling succeeds, not when the asynchronous
sweep completes successfully. This prevents repeated startup paths from
scheduling duplicate sweeps after a backfill failure.

If scheduling itself fails synchronously, the guard may reset so a later startup
path can retry scheduling. Once a task has been queued, async success or failure
does not reopen the guard.

Startup invocation happens after the native bridge-ready startup path has made
the existing video subsystem available. It schedules the sweep asynchronously
and returns startup control immediately. Completion writes concise diagnostics
to the existing startup trace path or equivalent internal diagnostics.

The startup call must have an independently disableable mode. Disabled mode must
return without scheduling work, without forcing a backfill run, and without
touching ffmpeg. The disable switch can be a constant/options object at the
composition site for Slice 5, but it must be easy to remove or turn off if
real-world startup friction appears.

## Runtime Flow

For each candidate artifact:

1. Skip non-`generated_video` artifacts before consuming the artifact cap.
2. Verify generated-video kind and local `video` blob availability.
3. Count only eligible generated-video artifacts considered for backfill toward
   `maxArtifacts`.
4. Check artifact cap and elapsed budget before starting work.
5. Compute missing roles from the manifest.
6. If no target roles are missing, record a skipped result.
7. Before each missing role attempt, check the elapsed budget.
8. If `poster` is missing, call the poster producer.
9. If `start_frame` is missing, call the role-targeted frame producer with only
   `start_frame`.
10. If `end_frame` is missing, call the role-targeted frame producer with only
   `end_frame`.
11. Record per-role results and continue until cap, budget, or candidate
   exhaustion.

Budget expiration stops the sweep before starting the next artifact or role. It
does not cancel a role already inside ffmpeg. The current role completes under
the existing producer/extractor timeout, and the service stops before starting
more work.

## Result Contract

Backfill returns a structured result so callers and tests can understand what
happened without reading logs only.

The result should include aggregate counts such as:

- scanned artifacts;
- eligible artifacts;
- artifacts skipped;
- artifacts attempted;
- role attempts;
- roles published;
- roles skipped because already present;
- role failures;
- artifacts stopped by cap;
- budget-exhausted flag.

It should also include bounded per-artifact diagnostics:

- artifact id;
- eligibility/skipped reason;
- roles missing at planning time;
- roles attempted;
- per-role result code;
- bounded message/diagnostic text.

Expected service-level outcomes are non-throwing where practical. Corrupt store
enumeration from `ArtifactStore.List()` can be reported as a failed backfill
result by the root/startup wrapper; it must not abort plugin startup.

## Failure Semantics

All backfill failures are diagnostic-only.

- A `poster` failure does not block frame role attempts for the same artifact.
- A `start_frame` failure does not block `end_frame`.
- An `end_frame` failure does not affect an already-published `poster` or
  `start_frame`.
- One artifact failure does not block later eligible artifacts unless the cap or
  budget has been reached.
- Missing ffmpeg records failures for the roles that require extraction and
  stops those attempts without affecting startup.
- Duplicate sidecar roles remain idempotent skips through existing publication
  policy, but the backfill service should avoid requesting roles known to
  already exist.

Backfill must never:

- append or mutate video job ledger records;
- submit, poll, cancel, or fetch provider jobs;
- infer provider payload fields;
- rehydrate provider URLs;
- change an existing artifact's primary `video` blob;
- convert startup into failure because a derivative could not be produced.

## Cancellation And Budget

Slice 5 uses budget checks, not aggressive cancellation, as the primary startup
safety mechanism.

The service checks elapsed time between artifacts and role attempts. If the
budget is exhausted, it stops before starting additional work and reports a
budget-exhausted result.

It must not cancel an in-flight ffmpeg process solely because the sweep budget
expired unless the ffmpeg cleanup path has been explicitly hardened in a future
reviewed slice. Existing per-role extractor timeouts still apply.

## Startup Guard

The startup one-shot guard has these semantics:

- separate from `ReconcileVideoJobsOnce()`;
- one scheduling success per process/root;
- async sweep completion status does not reset the guard;
- synchronous scheduling failure may reset the guard for a later retry;
- disabled mode schedules nothing;
- all startup wrapper exceptions are caught and logged as non-fatal.

This prevents duplicate sweeps when multiple startup paths race or retry while
preserving the ability to turn the feature off quickly.

## Tests

### Backfill Service Tests

Cover:

- skips non-`generated_video` artifacts;
- skips generated-video artifacts without a `video` role;
- skips generated-video artifacts with an unreadable `video` blob;
- skips artifacts with all target roles present;
- poster-only missing runs only poster;
- only `end_frame` missing runs only `end_frame`;
- mixed missing roles use deterministic order;
- artifact cap is honored;
- elapsed budget stops before starting additional artifact or role work;
- current in-flight role is not cancelled by budget expiration;
- per-role failure is non-fatal;
- per-artifact failure is non-fatal;
- structured result includes aggregate counts and bounded per-role diagnostics.

### Frame Producer Tests

Cover:

- role-targeted overload attempts only requested known frame roles;
- `start_frame` maps to `VideoFrameSelector.First`;
- `end_frame` maps to `VideoFrameSelector.Last`;
- unknown roles produce diagnostic failures;
- all-unknown role requests do not resolve the video blob, create temp files, or
  resolve ffmpeg;
- one requested role failure does not block another requested role.

### Startup Tests

Cover:

- backfill guard is separate from `ReconcileVideoJobsOnce()`;
- one-shot guard schedules only once after scheduling succeeds;
- async sweep failure does not reopen the guard;
- synchronous scheduling failure can be retried;
- disabled mode schedules nothing;
- startup source/lifecycle wrapper schedules asynchronously and catches/logs
  failures as non-fatal.

## Non-Goals

Slice 5 does not include:

- public route;
- MCP tool;
- native HTTP endpoint;
- Gallery UI changes;
- picker changes;
- GH NLE token behavior;
- arbitrary frame selection UI;
- provider payload audit;
- provider-poster ingestion;
- provider job reruns;
- existing-video provider re-fetch;
- ffmpeg packaging or licensing changes;
- generic derivative pipeline;
- generic artifact repair framework;
- whole-store repair on launch.

## Exit Criteria

Slice 5 exits when:

- startup schedules at most one bounded async backfill sweep per process/root;
- the sweep targets only eligible existing generated-video artifacts with local
  MP4 blobs;
- only missing sidecar roles are attempted;
- poster-only and one-frame-role-only gaps do not trigger unrelated extraction;
- artifact count and elapsed budget bounds are enforced;
- failures are observable and non-fatal;
- disabled startup mode is test-pinned;
- no provider jobs, provider payloads, public surfaces, GH/NLE surfaces, or
  generic repair abstractions are introduced.
