# Configurable fal: held-out acceptance at 53663942

Date: 2026-11-21 (UTC). Procedure: `docs/vision/fal-config-acceptance.md`, "Later paid acceptance evidence". Plan: Task 12 of `docs/superpowers/plans/2026-10-25-fal-model-definitions.md`. Freeze and sign-off: `2026-11-20-fal-config-freeze-53663942.md`.

## Result

- The frozen acceptance checker reports **accepted**, exit 0, no issues (`acceptance.json`).
- Two fal endpoints that the frozen build had never seen were added by JSON only and ran from both the Rook Vision panel and the installed MCP server.
- Source changes since the freeze commit: two definition files, the catalog list, and the two reports in this folder. No code, test, harness or packaging file changed, and nothing was rebuilt.
- Five paid jobs ran, all completed. Quoted cost USD 0.473 in total against a USD 1.00 cap. What fal actually billed is not known; Rook has no billing evidence.

## Endpoints

Selected by the maintainer on 2026-11-21T16:00:32Z, after the sign-off of 02:42:40Z, with the words "Yes, $1 cap".

| | Image | Video |
| --- | --- | --- |
| Model in Rook | `fal-ai/flux-2` (FLUX 2) | `fal-ai/pixverse/v6` (PixVerse V6) |
| fal endpoint | `fal-ai/flux-2` | `fal-ai/pixverse/v6/text-to-video` |
| Operation | `text_to_image`, synchronous | `text_to_video`, queued, lifecycle root `fal-ai/pixverse` |
| Definition file | `acceptance-image.json` | `acceptance-video.json` |
| Definition hash | `fe707259…5cfe14d1` | `237b4903…cc39c53f` |
| Controls beyond the common ones | Steps (integer), Guidance (number), Image size, Acceleration, Format (lists) | Audio (true/false), Negative prompt (text), Style, Prompt optimization (lists) |
| Pricing declared | USD 0.012 per megapixel, quoted at a ceiling of 2 megapixels | Per second, by resolution and audio: USD 0.025 to 0.115 |
| fal documents reviewed | `llms.txt` `9abcec50…`, OpenAPI `7a31f391…` | `llms.txt` `2ceb620d…`, OpenAPI `de055e7f…` |

The reviewed documents are saved under `held-out/docs/`. Both models were absent from the frozen catalog and from the frozen case data.

Inputs fal offers that the definitions leave out on purpose: FLUX 2 prompt expansion, safety-checker switch, custom pixel sizes and image count; PixVerse multi-clip and safety-checker switch. Their price effect is undocumented or they need account authorisation. A request that names one is refused.

## What was run

Evidence is under `artifacts/fal-config-acceptance/53663942/` (untracked); this round's files are in its `held-out/` folder. Commands and exit codes are in the `*.steps-and-exit.txt` files there.

| Step | Result |
| --- | --- |
| Catalog validation with the frozen qualifier | Exit 0, no diagnostics (`catalog-validation.json`) |
| Offline harness, planned inputs, before any spend | 13 of 13 cases pass (`conformance-prespend.json`) |
| Installed round 1, frozen empty catalog | Both models absent from the model lists; estimates refused |
| Installed round 2, definitions copied in | Both models listed; quotes equal the harness fingerprints; five bad requests refused by field name |
| Installed round 3, definitions removed | Capture byte-identical to round 1 |
| Installed round 4, definitions restored | Capture byte-identical to round 2 |
| Catalog copies (three) | `CodeHashesUnchanged : True` each time |
| Offline harness, inputs as actually used | 13 of 13 cases pass (`conformance.json`) |
| Acceptance checker | Exit 0, `accepted` (`acceptance.json`, `acceptance-checker.log`) |

The 13 cases are the four live jobs plus nine refusals: an undeclared option, a wrong type and an out-of-range value on each model, a value off the declared step, a list value fal offers but the definition does not, and a stale quote after the audio switch changes. Every refusal made zero provider calls.

## The paid jobs

| Job | Surface | Settings sent | Result | Quoted USD |
| --- | --- | --- | --- | --- |
| `4a41a179` FLUX 2 | MCP | size `square`, steps 20, guidance 3.5, format `jpeg` | 512×512 JPEG, 12 s | 0.024 |
| `445f0464` FLUX 2 | Panel | size `landscape_16_9`, rest default | 1024×576 PNG, 4 s | 0.024 |
| `a4cb7ee6` PixVerse V6 | MCP | 4 s, 360p, negative prompt, optimization `disabled` | 640×360 MP4, 4.04 s, no audio, 31 s | 0.10 |
| `61e3d9c2` PixVerse V6 | Panel | 4 s, 360p, negative prompt, style `3d_animation` | 640×360 MP4, 4.04 s, no audio, 31 s | 0.10 |
| `cef0fe0c` PixVerse V6 | Panel | all defaults (5 s, 720p) | completed | 0.225 |

The first four are the acceptance jobs. The fifth is listed in `evidence.json` under `other_paid_jobs` and is not one of the four; see deviation 2.

For each acceptance job the settings, pricing and definition hash saved in Rook's own job ledger equal the matching harness row, and the installed build's quote for the same inputs has the same fingerprint as the harness. The output files show the settings took effect: pixel size, file format, clip length and the absence of an audio track all match what was asked for.

## Deviations and open points

1. **Text-to-video, not image-to-video.** The plan prefers image-to-video so that a live job exercises image input. The endpoint proposed and approved was text-to-video. Image input rests on the synthetic fixture cases in the regression run, not on a live job.
2. **Five paid jobs, not four.** The first PixVerse panel job left every provider option at its default, so it carried one provider control where the checker needs two. It was run again with a negative prompt. Its quoted USD 0.225 counts against the cap.
3. **The panel's confirmation is not observed directly.** The panel does not log the request it sends. The panel jobs' inputs are read from the saved job records; the same inputs through the installed MCP estimate give the fingerprint and cap recorded, and the runtime accepts a submit only when its confirmation matches its quote.
4. **Few non-default values came from the panel.** The panel jobs changed one option on FLUX 2 and four on PixVerse. Non-default Steps and Guidance typed into the panel are proven only in the offline harness (`conformance-prespend.json`), which drives the real panel controls.
5. **One data file was moved out of the installed folder.** `venv\knowledge\metrics.json` appeared under the installed Python folder during round 2. The installed server writes it itself after ten tool calls in one process; no earlier run reached ten. It is usage counts, not code. It was moved unmodified to `held-out/stray-installed-file/` with a record of its hash and times. Before the move the inventory differed from the freeze by that one entry and nothing else.
6. **Rhino was restarted between jobs.** The MCP jobs, the first panel jobs and the last panel job ran in three Rhino processes. Loaded files were recorded for each (`round4-restored`, `final` and `final-2` `.loaded-paths.json`); all show the frozen build.
7. **No panel screenshot of absence this round.** That the models were absent before the copy rests on the MCP model lists and on the model-list screenshots from the freeze report. One panel screenshot of the FLUX 2 controls is saved in `held-out/panel/`.
8. **No conditional rule in either definition.** The plan's conditional-invalid case is covered by the synthetic fixture in the regression run.
9. **Pricing is a ceiling in two places.** fal does not say how it rounds megapixels, so FLUX 2 is quoted at 2 megapixels (USD 0.024) whatever the size. PixVerse uses the model page's rates; fal's general pricing table shows a lower figure (USD 0.005 per second) for the same endpoint.
10. **Two helper scripts outside the frozen tree.** The frozen capture utility admits no paid calls and no artifact reads, so the two MCP jobs and the job read-backs used separate scripts kept outside the repository. They start the installed interpreter the same way and call only the public `rook_tools_call` gateway. A spend ledger (`spend-ledger.json`) refused any submit that would pass the cap.
11. **Harness Python.** The offline harness ran with the `fix4-dependency-audit` test environment. The environment used for the freeze-time verification run no longer imports the MCP package.
12. **Not investigated:** Rook's video job ledger shows `duration_seconds: 0` in its older-format summary for configured video jobs, while the configured record beside it has the right value.

## Interface

The generated controls work but read poorly: two "Advanced" sections, long machine-written hints, provider spellings such as `landscape_16_9`, and a reset link under every control. These come from the shared control template, not from the definition files. The maintainer has asked for the template to be fixed as a separate code change after this acceptance.

## Not done

- No commit. The two definition files, the catalog list and this report are uncommitted.
- The plan's checkboxes are not ticked, and pull request 631 is still a draft.
