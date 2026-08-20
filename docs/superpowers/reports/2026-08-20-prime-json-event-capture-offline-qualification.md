# Prime JSON Event Capture Offline Qualification

**Date:** 2026-08-20
**Status:** V3 offline qualification retained; custody finalization follow-up verified offline
**Contact:** offline only; no Prime, model, Rook MCP, Rhino, or Grasshopper contact

## Scope

This qualification evaluates the opt-in campaign capture path defined by
[the approved design](../specs/2026-08-20-prime-json-event-stream-storage-efficiency-design.md).
Prime's emitted JSON event stream, Prime itself, Rook product behavior, the
Vessel run, and the V2 behavioral acceptance owner were not modified.

The capture owner:

1. reads bounded LF-delimited binary rows;
2. retains non-`message_update` rows byte-for-byte;
3. replaces exactly admitted cumulative assistant updates with closed delta
   records;
4. hashes and counts the original stream as it is observed;
5. uses a one-event monitor handoff; and
6. writes a closed custody sidecar before downstream admission.

The campaign runner selects this path only when a protocol explicitly admits
`primeEventCapture`. Historical protocols continue to retain
`operator/prime.jsonl` unchanged.

## Source Custody

The immutable input is the captured Prime JSON event stream from the sealed
multimodal Vessel run:

| Fact | Value |
|---|---:|
| Source rows | 74,473 |
| Source bytes | 3,543,087,572 |
| Maximum observed source row | 3,806,566 bytes |
| Source SHA-256 | `F79FF8A329993C9770B7E103B3F10620A6E118C5AD58E6184E9777EDFBFCAA3B` |
| Historical global manifest | 66/66, zero mismatches |
| Historical row manifest | 39/39, zero mismatches |
| Global manifest SHA-256 | `7BDD42FE284CDCF34AE101CE5550E9A1B5B7742A90F0437B5735C3FB5F67259D` |
| Row manifest SHA-256 | `FCD5205D361C1772ADB8C266CB33A9490F4679697CE28DE3B7D75636065B13A4` |

The source stream remains at its historical path and was never copied into the
qualification archive. The source SHA-256 establishes what the capture owner
observed while reading. It does not independently preserve or prove possession
of discarded cumulative update bytes; the immutable historical archive remains
the independent source for this offline specimen.

## V1 Preserved Failure

The first replay is preserved unchanged at:

```text
C:/UDEV/RookEvidence/2026-08-20-prime-json-event-capture-offline-qualification-v1
```

Its protocol SHA-256 is
`8082BA9D7133423FC2AC803097D373CCB10E7883FA120519926231AF375126BF`.
It stopped with `assistant_reconstruction_mismatch` after both compact streams
had been written. It produced nine files totaling 73,092,705 bytes and did not
reach result adjudication or evidence-manifest sealing.

The retained bytes localized the problem. All 29 assistant messages had exact
content reconstruction, but every terminal checkpoint finalized envelope
metadata that was not present at `message_start`: provider usage, stop reason,
and, where applicable, response identity. The reconstructor incorrectly
required the starting envelope to equal the terminal envelope.

The correction follows the approved contract: compact deltas must reconstruct
the exact terminal `content`, while the exact retained `message_end` remains
authoritative for final envelope metadata and is returned as the terminal
message. A RED regression reproduced this exact case before the implementation
changed. V1 evidence and protocol bytes were not rewritten or reused.

## V2 Result And Review Refusal

V2 used a fresh protocol and evidence root. Its harness returned `qualified`,
but independent implementation review refused that result. The reviewer found
that custody verification retained all rows in memory, the passthrough oracle
called the transformer under test, and the size ratio omitted the custody
sidecar. The reviewer independently confirmed that V2's captured specimen was
substantively exact, but its proof boundary was insufficient.

V2 remains preserved unchanged. The figures produced by its original harness
were:

| Fact | Value |
|---|---:|
| Status | `qualified` |
| Retained rows | 74,473 |
| Retained bytes | 36,542,989 |
| Retained SHA-256 | `90407E778688FC945AFD32B3F5D8AB3F4A00582DED072CA1E9FC3866088246C1` |
| Compacted updates | 74,143 |
| Raw-fallback updates | 0 |
| Retained ratio | 1.0313882527% |
| Size reduction | 98.9686117473% |
| Qualification phase duration | 47.75 seconds |

The ratio above is the historical V2 stream-only figure. Including V2's
564-byte custody sidecar gives 1.0314041710% retained and 98.9685958290%
reduction.

## V3 Result

V3 used a fresh protocol and evidence root after two bounded corrections:

- custody verification now streams hashes, counts, maxima, and retained-row
  validation without accumulating row bodies; and
- a qualification-owned row-paired oracle independently projects every compact
  source event without calling `transform_prime_row`.

| Fact | Value |
|---|---:|
| Harness status | `qualified` |
| Source and retained rows | 74,473 / 74,473 |
| Compact stream bytes | 36,542,989 |
| Custody bytes | 564 |
| Total persisted bytes | 36,543,553 |
| Retained SHA-256 | `90407E778688FC945AFD32B3F5D8AB3F4A00582DED072CA1E9FC3866088246C1` |
| Exact compact projections | 74,143 |
| Byte-identical passthrough rows | 330 |
| Raw-fallback updates | 0 |
| Retained ratio | 1.0314041710% |
| Size reduction | 98.9685958290% |
| Qualification phase duration | 57.266 seconds |

The V3 persisted result exceeds the frozen 95% reduction requirement. The earlier
gzip-only measurement retained 727,134,876 bytes and reduced the stream by only
79.48%, so compression alone would not have met that requirement.

Replay A and replay B produced byte-identical retained streams and byte-identical
custody sidecars:

```text
compact stream SHA-256
90407E778688FC945AFD32B3F5D8AB3F4A00582DED072CA1E9FC3866088246C1

custody sidecar SHA-256
FBF53094799E849A45B2361D830682A6E0A0DD4E2E68D2D81D4AD8548408C850
```

## Semantic Parity

The V3 qualification established:

- exact reconstruction of all 29 terminal assistant message values;
- 74,143 independently projected compact rows with exact subtype, content
  index, delta, end content, tool-call, source-row, and source-byte equality;
- 330 byte-identical passthrough rows;
- equal normalized V2 source events;
- equal lifecycle and same-session compaction classification;
- equal tool execution, result, error, checkpoint, and terminal history;
- equal latest terminal receipt selection;
- equal final fenced observation.

Raw and compact representations produced identical normalized source events,
receipt selection, and fenced-observation selection. Shadow evaluation was not
independently recomputed by this storage qualification and remains owned by the
unchanged V2 evaluator.

The selected receipt on both paths is:

```text
78e858015aeb627e69d4fe569cbaf37f
```

The unchanged V2 owner sealed separate raw and compact source copies. Their
closure files intentionally differ only in `runtime_log_sha256`:

```text
raw V2 source SHA-256
9D2DFFA9AAD4D0BD6FD14E6294A49A263EF1593D154F96AB65E4FE0FDD02E9DF

compact V2 source SHA-256
D00A1A126EB7CE383593C58190C47A38584DC6AC0BE77335B8AAA5529A3EAE56
```

No new semantic classification or acceptance vocabulary was introduced.

## Boundedness

The frozen capture limits are:

```text
maximum source row       67,108,864 bytes
source read chunk            65,536 bytes
monitor queue                     1 event
```

Oversized terminated rows, oversized unterminated rows, and a stalled consumer
have causal tests. A separate raw-debug regression verifies that custody
admission remains below a fixed memory ceiling when both retained and raw files
are much larger than that ceiling. The sealed specimen's largest row was
3,806,566 bytes.

No operating-system peak-memory measurement was retained, so this report makes
no empirical peak-RSS claim. The bounded-memory claim is instead the qualified
mechanical contract: chunked LF detection refuses above the row ceiling, and
the live handoff applies one-event backpressure rather than accumulating an
unbounded queue.

## Evidence

V3 evidence root:

```text
C:/UDEV/RookEvidence/2026-08-20-prime-json-event-capture-offline-qualification-v3
```

Key hashes:

| Artifact | SHA-256 |
|---|---|
| V3 protocol | `949119BC1959E4E937CAEE97198470FA32E07BAB297D7F3C679BDFC7AEE066EC` |
| Qualification result | `C7E18129C1E72A6CFB4CA60B7034B2664CE4BDE6093DAB03D9C613B1A0D3D426` |
| Source custody | `159B350C389E0EE9C461A46C252E434511EDE77348026293290A6C7A459CFAF7` |
| V2 parity | `8DDE60736EE4636DCE066A118000794CCFA39E62FEEEF5F97CB97C51B74F642B` |
| Evidence manifest | `1063B396B0BD580C52D30096FDB0A30D5D194D9ADF7D620E216645BD92C653FB` |

The sealed evidence manifest independently verifies 13/13 entries with zero
mismatches.

## Implementation Custody

| Owner | SHA-256 |
|---|---|
| V3 replay capture module | `6D5537386F391578650B276A4A25FC224F7ECBE14B7767BE5AB886B780439F94` |
| Current capture module after custody finalization follow-up | `3C565D1264C01951B8ED65CF868F536F758537F989500EB3FAF2751B3F159329` |
| Campaign runner | `CB0F4076A6812ABF6C8356DB874F1A04E90B37EA029B1C9E5262780E5C9A221F` |
| Qualification harness | `1F542B1CE056776719495883DBFF78B74BF028EB6EFEEB1C23DD6F29FD9F7E6A` |
| Unchanged V2 owner | `55211B778B44C96729A21D9DAE430B2883F4636520C030E1EBFD3B8F896508FF` |
| Approved design | `E5FAAE11FDCB40C184F0478E611D77F777B2C8E552B99A6736555592BC0FDC63` |
| Implementation plan | `C1EDF40BCD66505819CBA49FDAC2E9706B3287245A3B826523602F7FF2FF16F5` |

Implementation lineage:

```text
be3b4de0  feat: add compact Prime event transformation
1c620abd  feat: add bounded Prime event capture custody
f64f255a  feat: integrate compact Prime capture
092acc83  test: freeze Prime capture qualification
0ac26452  fix: reconstruct terminal Prime message metadata
0749eec8  fix: bound and independently verify Prime capture
7dd4a1a1  test: freeze reviewed Prime capture qualification
```

## Verification

The full offline suite passed:

```text
369 passed, 11 existing dependency warnings
```

The V3 archive retains its own precontact result:

```text
251 passed in 5.71s
stderr: empty
```

All three Python owners compile. JSON protocols parse. Git whitespace checks
pass. The Rook worktree at `7dd4a1a1`
and the untouched Prime evaluation worktree at
`739400844f8f3f280414b0c7b9c65797208815d3` were clean before this report.

The qualification harness contains no model, product-server, browser, or live
CAD dependency. Its only subprocess is the frozen offline pytest command. The
result records `liveContact: false`; no Prime process, model server, Rook MCP
server, Rhino process, or Grasshopper process was launched or contacted.

## Disposition

The V3 harness qualified the compact capture path offline for this sealed
74,473-row Vessel specimen and for the named current consumer boundaries. It is
opt-in and does not change historical capture behavior. The staging-only
follow-up publishes complete custody only after its temporary file closes
successfully; causal write, flush, and close failures leave no admissible
custody path. It does not change compact transformation or retained-stream bytes,
so V3 evidence remains unchanged and no V4 replay was performed.

This result does not prove byte reconstruction of discarded cumulative
`message_update` rows, universal compatibility with future Prime event shapes,
or a live-campaign deployment. Unknown or open update shapes remain raw
fallbacks; malformed or oversized input remains fail-closed. No live smoke is
authorized by this qualification.
