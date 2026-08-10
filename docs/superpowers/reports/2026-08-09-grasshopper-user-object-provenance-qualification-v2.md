# Grasshopper User-Object Provenance Qualification V2

## Purpose and authorization

This V2 qualification repeated the same six-specimen, metadata-only observation after
correcting the consumed V1 probe's Python-string normalization defect. The operator
authorized exactly one read-only `/execute` request using target SHA-256
`63CE846465A22E03BD1DE9BCB074B3FA9E5A34FCA68BA5A2F619718EBBFE392A` and
manifest SHA-256
`A3BD72712D2D09E56315384F2DADEC2497C5B1257CEFCE8BFEE786D17971B624`.
The request completed at `2026-08-10T00:49:40.108621+00:00`.

## V2 correction and evidence custody

The only behavioral probe correction was
`BitConverter.ToString(digest).Replace("-", "")` to the Python-string operation
`.replace("-", "")`; the only other probe delta was the V2 root path. A new causal
regression exercised the complete `main()` path with `BitConverter.ToString()` returning
a Python `str`: it failed against V1 behavior and passed after the correction. The V1
lane, report, and evidence artifacts remain unchanged.

## Artifacts and SHA-256 values

- `user-object-provenance.json`:
  `E7BC4124D1029D9F50721FB45B3E1079317CDC1901A0332B635532681CCE04BD`
- `invoke-result.json`:
  `DCA890C23199698AFFE97DC8A43867CE9E91295A7020DFBE6A51B24332104A20`
- `stderr.txt` (empty):
  `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855`

Both JSON artifacts passed strict UTF-8 and duplicate-key checks. HTTP status was `200`,
the returned envelope had `success=true`, and its exact sentinel matched the independently
computed artifact hash. Returned `stderr` was empty, `objectsCreated=0`, and
`objectIds=[]`.

## Target, budget, and canvas equality

The exact target was Rhino PID `38672`, native port `55902`, and document serial
`268435457`. The budget matched exactly: one `/execute`; six each of proxy emission,
user-object construction, temporary instance creation, proxy-GUID assembly lookup, and
instance assembly lookup; two canvas count reads; and zero search, insertion, solution,
model, retry, and cleanup calls. Canvas object count remained `0 → 0`.

## Six ordered complete specimens

| Path group (evidence only) | Proxy GUID | Bytes | Content SHA-256 |
|---|---|---:|---|
| `ladybug_grasshopper` | `003934c7-7c91-40c3-a35d-8b672e32bf7a` | 4427 | `1E85CB70DEEB0F1E76E3FB133A55EC252D5E42ABDE0F202D338FB1CA7D264FDB` |
| `honeybee_grasshopper_core` | `01a59900-f860-4d3b-a2a4-629a7b867a94` | 3432 | `A102E78CF1A99997D60ACE9FFB3BD8C378D9451904E73C98CFA75E34B1F54911` |
| `honeybee_grasshopper_energy` | `049a829b-2181-4062-b757-5f30ff7dbf18` | 5317 | `01C8D126BCDEEBD82ABE662CFDEE45181F0A12EB33C1D21B7A150011FD85594D` |
| `honeybee_grasshopper_radiance` | `003e5f4f-95ae-42ad-8178-189d51fb0433` | 3115 | `D2083ED01CEE00F5CA5D7498B68734B2B10B6D6002E6C940DCD37301106FC767` |
| `dragonfly_grasshopper` | `00653abd-3197-4917-b751-60698f37381a` | 3899 | `EED1FEE3D5DEC08F1D57CC1007B94DF3E249CD5AC3D4809B1D569700B2AF7F1C` |
| `fairyfly_grasshopper` | `06348dc2-a44c-42f4-a5d5-870fc56cfb27` | 3353 | `066F8BF953E4AE28BFD299E2002FD932916B75197376AC4AED0C4BD3266D550E` |

All six selectors matched their exact emitted proxy GUID, every proxy kind was
`UserObject`, and every normalized retained path matched proxy `Location` and
`GH_UserObject.Path`. All six specimens were complete and `probeComplete=true`.

## Assembly and implementation observations

`FindAssemblyByObject(proxy GUID)` returned `not_found` for all six. Each temporary
instance resolved to `GhPython.Component.ZuiPythonComponent` in `GhPython.gha`, version
`8.34.26215.11001`. Each observed user-object `BaseGuid` equaled the temporary
`ComponentGuid` (`410755b1-224a-4c1e-a407-bf32fb45ea7e`). Those fields identify the
shared execution implementation, not the package that supplied a `.ghuser` file.

## Identity-handoff decision

**Identity handoff closed with source-kind-specific provenance variants.** Compiled
`.gha` components may use authoritative assembly provenance. A `.ghuser` component uses
its current-installation proxy GUID plus exact user-object path, description, and content
length/fingerprint. `BaseGuid` and runtime assembly remain implementation metadata.

## Claims and non-claims

This proves that the installed host exposes enough direct metadata to distinguish the
six retained `.ghuser` identities without search, archive parsing, inference, or canvas
mutation. It does not make path-derived proxy GUIDs portable, establish `BaseGuid`
uniqueness, or establish authoritative package, author, family, or package-version
identity. Folder names remain environmental evidence only. Raw `Data` bytes were never
retained. This qualifies metadata available for a future endpoint; it does not prove the
current `/gh/batch-component-info` response exposes that provenance.

## Next gate

Stop for independent evidence review. Only after that review may the discovery
specification pin the source-kind-specific identity handoff and proceed to a production
implementation plan. No further host run is needed for this qualification.
