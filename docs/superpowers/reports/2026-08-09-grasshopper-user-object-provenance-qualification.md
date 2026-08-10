# Grasshopper User-Object Provenance Qualification

## Purpose and authorization

This qualification tested the host metadata available for six exact retained `.ghuser`
proxy identities. The operator authorized exactly one read-only `/execute` request for
target SHA-256
`63CE846465A22E03BD1DE9BCB074B3FA9E5A34FCA68BA5A2F619718EBBFE392A`.
The request completed on 2026-08-10 at `00:00:40.123489+00:00`. No model call,
search, canvas mutation, retry, cleanup, or second host request occurred.

## Artifacts and SHA-256 values

- `user-object-provenance.json`:
  `72D734E11E9E7CC1408020C7DA2CFD42F89712750713025D41C952BB22E4FB26`
- `invoke-result.json`:
  `496BCD9A304C1E52B18A0A1EE5D16BDA734856C743F159BAFBF0DA4751CE17EB`
- `stderr.txt` (empty):
  `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855`
- Source discovery evidence:
  `254A9BF5A8EEE5DCCA72A37AD08DF20EDF63271F55E2F14AC4587BC180481988`

Both JSON artifacts decoded as strict UTF-8 with no duplicate keys. The outer HTTP
record is status `200` with `success=true`; its exact sentinel contains the independently
recomputed compact-artifact hash. `stderr` is empty, `objectsCreated=0`, and
`objectIds=[]`.

## Target, call budget, and canvas equality

The exact target was Rhino PID `38672`, native port `55902`, and Rhino document serial
`268435457`. The observed budget was exactly one `/execute`, six each of
`EmitObjectProxy(Guid)`, `GH_UserObject(path)`, `proxy.CreateInstance()`,
`FindAssemblyByObject(Guid)`, and `FindAssemblyByObject(instance)`, plus two canvas
object-count reads. Search, insertion, solution, retry, cleanup, and model counts were
all zero. Canvas object count was `0` before and `0` after.

## Six ordered specimen outcomes

| # | Evidence-only path group | Proxy GUID | Host name | Proxy-GUID assembly | Temporary-instance assembly | Complete |
|---:|---|---|---|---|---|---|
| 1 | `ladybug_grasshopper` | `003934c7-7c91-40c3-a35d-8b672e32bf7a` | LB Legend Parameters | `not_found` | GhPython `8.34.26215.11001` | No |
| 2 | `honeybee_grasshopper_core` | `01a59900-f860-4d3b-a2a4-629a7b867a94` | HB Door | `not_found` | GhPython `8.34.26215.11001` | No |
| 3 | `honeybee_grasshopper_energy` | `049a829b-2181-4062-b757-5f30ff7dbf18` | HB Apply Room Schedules | `not_found` | GhPython `8.34.26215.11001` | No |
| 4 | `honeybee_grasshopper_radiance` | `003e5f4f-95ae-42ad-8178-189d51fb0433` | HB Ambient Resolution | `not_found` | GhPython `8.34.26215.11001` | No |
| 5 | `dragonfly_grasshopper` | `00653abd-3197-4917-b751-60698f37381a` | DF Apply Facade Parameters | `not_found` | GhPython `8.34.26215.11001` | No |
| 6 | `fairyfly_grasshopper` | `06348dc2-a44c-42f4-a5d5-870fc56cfb27` | FF Model | `not_found` | GhPython `8.34.26215.11001` | No |

Each incomplete outcome has the same retained `Data` property error:
`builtins.AttributeError: 'str' object has no attribute 'Replace'`. The host runtime
type is `System.Byte[]`, but `byteLength` and `sha256` are therefore null. Prior proxy,
path, description, user-object, temporary-instance, and assembly observations survived
the projection failure.

## Observed identity relationships

All six selectors matched the exact emitted proxy GUID; every proxy kind was
`UserObject`; and each normalized retained path equaled both proxy `Location` and
`GH_UserObject.Path`. Every user-object `BaseGuid` equaled the temporary instance
`ComponentGuid` in this sample (`410755b1-224a-4c1e-a407-bf32fb45ea7e`). That equality
is an observation, not a portable identity rule. Proxy GUIDs remain current-installation,
path-derived identities.

## Proxy-GUID and temporary-instance assembly results

`FindAssemblyByObject(proxy GUID)` returned `not_found` for all six specimens.
`FindAssemblyByObject(temporary instance)` returned `found` for all six and resolved the
same base runtime: `GhPython.Component.ZuiPythonComponent` in `GhPython.gha`, assembly
version `8.34.26215.11001`. Its projected `GH_AssemblyInfo` package-like fields were
empty and its ID was the zero GUID. This identifies the instantiated base implementation;
it does not identify which package supplied the `.ghuser` file.

## Available and unavailable provenance fields

Direct host evidence supplies proxy GUID, `LibraryGuid`, original path, description
scalars, exposure, `SDKCompliant`, user-object `BaseGuid`, temporary component/runtime
type, and base runtime assembly location/version. It does not supply authoritative
`.ghuser` package, author, family, or package-version identity in these specimens.
Folder/group names are retained environmental evidence only. Raw `Data` bytes were not
retained. Their length and hash are unavailable because the projection failed.

## Identity-handoff decision

**Qualification incomplete.** Transport correlation, the closed call budget, canvas
equality, and all six identity equations passed, but `probeComplete=false` because all
six required `Data` byte projections failed. This capture cannot select either closed
identity-handoff conclusion.

## Claims and non-claims

The capture proves that exact `.ghuser` proxies can be resolved, constructed temporarily,
and correlated with their base GhPython implementation without canvas mutation. It also
proves that proxy-GUID assembly lookup alone returns no assembly provenance for these six
user objects. It does not establish portable proxy identity, package/author/family/version
identity, `BaseGuid` uniqueness, or a production response contract. In particular, it
qualifies metadata available for a future endpoint implementation; it does not prove that
the current `/gh/batch-component-info` response exposes this provenance.

## Next gate

Stop for independent evidence review. Do not amend the discovery specification or write
a production implementation plan from this incomplete capture. Any proposal to correct
the disposable byte projection or seek another authorization is a separate reviewed
decision; this consumed evidence remains unchanged.
