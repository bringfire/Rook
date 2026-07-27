# RookBIM CreationGUID probe result

**Status:** Completed evidence; identity decision proposed and awaiting reviewer approval

**Probe build:** Rook and RookBIM 1.5.16.0 at `85c6df4f4f01dfd76a0a100dd4a201ce80ab96b2`

**Host process:** 37368

**UTC interval:** 2026-07-27T14:41:49.1621795Z to 2026-07-27T15:30:23.6684819Z

## Provenance

| Component | Observed version |
|---|---|
| Revit | Autodesk Revit 2024 |
| Revit build | 24.3.40.26 |
| Revit API | 24.3.40.0 |
| Rhino | 8.33.26188.13001 |
| Grasshopper | 8.33.26188.13001 |
| Rhino.Inside.Revit | 1.35.9651.15514 |
| Rook core | 1.5.16.0 |
| RookBIM module | 1.5.16.0 |

The report-local aliases below are opaque equality labels. They are not hashes and are not comparable with aliases from any other probe run.

## Capture matrix

Notation: `S:value` means the independent read succeeded with that value; `NA` means not applicable; `NT` means deliberately not attempted. Creation evidence is shown as `first/second; nonempty; stable; alias`. A successful path read with alias `none` returned no comparable path.

| Case | Class | Creation evidence | Document path | Central path | W / D / Cloud / Family | Central / Local | ModelPath | Bounded failure evidence |
|---|---|---|---|---|---|---|---|---|
| `saved_project_initial` | `saved_non_workshared_project` | `S/S; yes; yes; creation-004` | `S:path-005` | `failure:none` | `S:false / S:false / S:false / S:false` | `S:false / S:false` | `unknown` | `central_model_path`; `Autodesk.Revit.Exceptions.InvalidOperationException`; `-2146233088` |
| `saved_project_reopen` | `saved_non_workshared_project` | `S/S; yes; yes; creation-004` | `S:path-005` | `failure:none` | `S:false / S:false / S:false / S:false` | `S:false / S:false` | `unknown` | `central_model_path`; `Autodesk.Revit.Exceptions.InvalidOperationException`; `-2146233088` |
| `file_central` | `file_workshared_central` | `S/S; yes; yes; creation-001` | `S:path-002` | `S:path-002` | `S:true / S:false / S:false / S:false` | `S:true / S:false` | `file` | none |
| `file_local` | `file_workshared_local` | `S/S; yes; yes; creation-001` | `S:path-001` | `S:path-002` | `S:true / S:false / S:false / S:false` | `S:false / S:true` | `file` | none |
| `file_local_reopen` | `file_workshared_local` | `S/S; yes; yes; creation-001` | `S:path-001` | `S:path-002` | `S:true / S:false / S:false / S:false` | `S:false / S:true` | `file` | none |
| `copied_central` | `file_workshared_central` | `S/S; yes; yes; creation-001` | `S:path-003` | `S:path-003` | `S:true / S:false / S:false / S:false` | `S:true / S:false` | `file` | none |
| `detached` | `detached` | `S/S; yes; yes; creation-001` | `failure:none` | `S:none` | `S:true / S:true / S:false / S:false` | `NT / NT` | `file` | `basic_file_info_extract`; `Autodesk.Revit.Exceptions.FileArgumentNotFoundException`; `-2146233088` |
| `saved_family` | `saved_family` | `S/S; yes; yes; creation-002` | `S:path-004` | `failure:none` | `S:false / S:false / S:false / S:true` | `S:false / S:false` | `unknown` | `central_model_path`; `Autodesk.Revit.Exceptions.InvalidOperationException`; `-2146233088` |
| `unsaved_project` | `unsaved_project` | `S/S; yes; yes; creation-005` | `S:none` | `failure:none` | `S:false / S:false / S:false / S:false` | `NA / NA` | `unknown` | `central_model_path`; `Autodesk.Revit.Exceptions.InvalidOperationException`; `-2146233088` |
| `unsaved_family` | `unsaved_family` | `S/S; yes; yes; creation-003` | `S:none` | `failure:none` | `S:false / S:false / S:false / S:true` | `NA / NA` | `unknown` | `central_model_path`; `Autodesk.Revit.Exceptions.InvalidOperationException`; `-2146233088` |
| `replacement_same_path` | `saved_non_workshared_project` | `S/S; yes; yes; creation-005` | `S:path-005` | `failure:none` | `S:false / S:false / S:false / S:false` | `S:false / S:false` | `unknown` | `central_model_path`; `Autodesk.Revit.Exceptions.InvalidOperationException`; `-2146233088` |

Every property above was read through its own exception boundary. `CreationGUID` was read twice for every case. A central-path failure on an inapplicable non-workshared document did not hide later reads or alter the capture result.

## Fixed equality relations

| Left | Right | Same creation | Same document path | Same central path | Unavailable component |
|---|---|---:|---:|---:|---:|
| `saved_project_initial` | `saved_project_reopen` | yes | yes | unavailable | yes |
| `file_central` | `file_local` | yes | no | yes | no |
| `file_local` | `file_local_reopen` | yes | yes | yes | no |
| `file_central` | `copied_central` | yes | no | no | no |
| `saved_project_initial` | `replacement_same_path` | no | yes | unavailable | yes |

## Suitability assessment

| Criterion | Evidence | Result |
|---|---|---|
| Creation value is readable, nonempty, and stable on repeated reads | All eleven cases returned two successful, equal, nonempty reads. | pass for observed cases |
| Central and standard local share creation and canonical central-path evidence | `file_central`, `file_local`, and `file_local_reopen` share `creation-001` and central `path-002`. | pass |
| Saved document remains stable after close/reopen | The saved project retained `creation-004` and `path-005`; the local retained `creation-001`, local `path-001`, and central `path-002`. | pass for saved projects and file locals |
| Copied central is distinguished by the composite | The original and copy share `creation-001`, but use central paths `path-002` and `path-003`. | pass |
| Different document at the same path is distinguished by creation | The original and replacement share `path-005`, but use `creation-004` and `creation-005`. | pass for saved projects |
| Saved family meets every class-specific durability criterion | The family had stable repeated reads and a saved path, but this matrix did not include a saved-family close/reopen or same-path replacement pair. | not established |
| Detached evidence is eligible for authorization | The detached case retained creation evidence but had no comparable saved document path. Detached evidence is descriptive only. | rejected by policy |
| Unsaved evidence is eligible for authorization | Both unsaved classes had creation evidence but no comparable path. | rejected by policy |

## Proposed identity decision

**Proposed — awaiting reviewer approval:** select outcome 2, **class-limited composite**.

- Propose `revit_creation_guid_central_path_v1` for file-workshared central and local documents.
- Propose `revit_creation_guid_document_path_v1` for saved non-workshared projects.
- Keep saved families fail closed until a family-specific close/reopen and replacement probe closes the missing durability evidence.
- Keep detached and unsaved documents fail closed.
- Revit Server and cloud infrastructure were unavailable in this run; their typed sources remain unapproved pending class-specific live evidence.
- Path-only authorization remains prohibited.

This is evidence for review, not authorization to implement or deploy a production identity resolver.

## Privacy and lifecycle validation

- Eleven required cases are present exactly once; no cases are missing.
- Five fixed equality relations are present.
- The durable report contains no model or family title, filename, raw or normalized path, raw Revit GUID, deterministic identity hash, exception message, or stack trace.
- The generated operational session identifier was deliberately omitted from this document.
- Failure evidence is limited to closed stage, exception type, and HResult fields; no failure text contains a newline.
- Probe completion reported `rawStateCleared=true`; the in-memory alias-to-value tables were destroyed.
- The temporary detached result is descriptive only and is not promoted to identity evidence.
