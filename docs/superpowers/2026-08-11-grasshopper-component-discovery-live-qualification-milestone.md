# Grasshopper Component Discovery Live Qualification Milestone

- Qualified merge: `364bd50c74253f78caba16de753473c0f8ba9198`.
- Frozen target: Rhino PID `61960`, native port `49813`, document serial `268435457`, readonly profile.
- Budget: five host calls; zero model calls, mutations, retries, fallbacks, cleanup, or additional inspection.
- Evidence root: `C:/Users/bring/AppData/Local/Temp/rook-gh-discovery-postmerge-364bd50c`.
- Original evidence manifest SHA-256: `FA1E4D0EFF0BFA4A40FDE47505AAF2A13CA6D24352DF4B8598ACCE8B28CEF0E2`.

## Successful Transaction

The retained row performed exactly: exact `Angle` discovery; name metadata for `Angle`; bounded native `Range` discovery; one GUID metadata batch for the frozen compiled Range GUID and the first returned `user_object`; and the independent audit GET.

Exact `Angle` discovery returned two distinct compiled candidates. Name metadata returned `ambiguous_name` with both GUIDs and selected neither. The `Range` search returned `10` of `204` matches with `truncated=true`; its first `user_object` in native order was `LB Color Range` at index `2`, GUID `3588060f-3cc2-4118-b082-b2b4da21d1dd`. The correlated metadata batch returned two successes in request order: compiled Range GUID `9445ca40-cc73-4861-a455-146308676855` with assembly provenance, and the selected `.ghuser` with exact path, `2869` content bytes, and content SHA-256 `B8FB2F2B16F608DD90CADF766B05A0A8A25C72CD97889284095B173DA0B14000`.

The audit GET returned HTTP `200`, stable GUID ordering, and the unchanged component key set. It observed `1890` scanned proxies, `775` deprecated entries, `198` obsolete entries, `487` hidden entries, and `775` returned components.

## Runtime Custody

`runtime-custody.json` is a clearly labeled post-run observation, not part of and not retroactively inserted into the original manifest. It records matching merge/installed `server.py` hashes (`E0F6453B4BC95EC428D56A254D0E44AA85A4DC7A3885C749C58B80ABB2329DB8`) and matching merge-build/deployed `net48` payload hashes (`372D80DBE7A45FB8DB6E9100BBE72F97CFE7712804DD35B6C82611271E677E5D`). It also records the matching current `net8.0` artifacts (`1111C48FB48ED5C23097C7A7606D7D5CA75BF93A3B6E51BFB501A79DC921D5E4`). Its own SHA-256 is `8498CD10EFEAEF2C2C63CEDFAF8270073F087679765AA6A59D8524741DDD5EF9`.

This post-run comparison corroborates current on-disk deployment only. Because the original preflight output was not retained in the evidence directory, it does not independently prove which `Rook.rhp` bytes Rhino had loaded during the qualification.

## Evidence Hashes

| Artifact | SHA-256 |
|---|---|
| `row.json` | `ED2B8597D099C9EAAE22440F7DBAEA0FB6DEA1C8527D35CA7F428E800077DB47` |
| `call-1-gh-library-angle-exact.json` | `162D63E8B21A9901EE50162B6E49F200D595269470D6246462B3482B17006493` |
| `call-2-gh-batch-angle-name.json` | `056EE3B3FD1CCACE4F1D39B08A0C67276569C62900B691A611C3A5AE6B4FB2C4` |
| `call-3-gh-library-range-limit10.json` | `7EFAF14C993F54A40344668575E83275284BC6A1AE72EC0837568802A9C7B73F` |
| `call-4-selection.json` | `661ED9E4F6F71DA4D6B2F1237D9334C7728473309C197A181ED634B1E0CF1803` |
| `call-4-gh-batch-range-compiled-user-object.json` | `F055310FCB3D714B6267E7B9563E47D15F80BE13A4DAFA3DF4907223F34708F7` |
| `call-5-audit-body.json` | `6F551EC413D3DE8DD3E14864931E1A446AC07320AB6B05493203D44119E9C32A` |
| `call-5-audit-http.json` | `2203B810012C8455BDBE10474F255244C1FA24C3FE4D42057F551B539A35317C` |
| `qualification-summary.json` | `18366A9B923EF09DB1A4091D35D0A6B4212B01401D2B6BA25A1753F45D1C43F6` |
| `evidence-hashes.json` | `FA1E4D0EFF0BFA4A40FDE47505AAF2A13CA6D24352DF4B8598ACCE8B28CEF0E2` |
| `runtime-custody.json` (post-run) | `8498CD10EFEAEF2C2C63CEDFAF8270073F087679765AA6A59D8524741DDD5EF9` |

## Proven Claims And Non-Claims

For this installed catalog and frozen target, the qualification proves native ranked discovery, distinct duplicate exact-name candidates, ambiguity refusal without guessing, truthful counts and truncation, live third-party `.ghuser` participation, direct discovery-GUID handoff to correlated metadata, compiled and `.ghuser` provenance, absence of knowledge hints from both authoritative tools, compatible audit behavior, and no qualification-owned canvas mutation.

It does not prove model efficiency, semantic task performance, mutation by selected GUID, coverage of every installed plugin, cross-install identity or repeatability, or the exact binary loaded during the run beyond the retained behavioral evidence and post-run custody qualification above.

Discovery and identity-handoff qualification stops here. No further discovery-code change or host rerun is warranted. The next meaningful experiment is a separately reviewed frozen model task against this qualified surface: control model first, then the local-model comparison.
