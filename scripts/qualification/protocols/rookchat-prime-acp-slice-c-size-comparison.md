# Slice C: Original versus 8x Diagnostic Proposal

Preparation only. Both live arms require separate explicit authorization of
this frozen comparison. V1 remains FAILED; accepted A+B remains unchanged.
This does not alter Slice C acceptance or qualify a live panel-to-model round trip.

## Hypothesis and single changed variable

Hypothesis: increasing the raster dimensions of this particular diagram can
change the answer to its spatial question under otherwise identical requested
conditions. Test only original 160x112 versus nearest-neighbor 1280x896.
Every source pixel becomes an identical 8x8 RGB tile; no colors, geometry,
labels, cropping, sharpening, prompt hints or added information change.
The PNG byte length necessarily changes. No provider detail override is added;
the pinned converter continues to select detail=auto.

This tests a limited input-size comparison, not reliability or a causal fix.
One sample per condition cannot separate image-size effects from stochastic
generation, order, time, caching or unobserved provider behavior. In particular,
neither a larger-image success nor SDK source inspection proves what went wrong
in historical V1 or how OpenAI processed its image.

## Frozen arms

Fixed order: original first (protocol v2), enlarged second (protocol v3).
One fresh Prime process/session and one prompt per arm, no retries or follow-ups.
The v2/v3 names identify fresh diagnostic executions, not replacements for V1.

| Input | Original (v2) | Enlarged (v3) |
| --- | --- | --- |
| File under scripts/qualification/fixtures | slice-c-image-01.png | slice-c-image-01-8x.png |
| Dimensions | 160x112 | 1280x896 |
| Encoding | PNG RGB | PNG RGB |
| Bytes | 380 | 4815 |
| SHA-256 | 55E248996331234C769031ACA810A1D5FEF868EFDC4A93CADEA0D295E75EFD47 | 7819C70319FD79B419D15693E544DB3423040CD2CDDF63F7BB4CE12A66171855 |
| Conversation ID | cccccccccccc4ccc8cccccccccccccc2 | cccccccccccc4ccc8cccccccccccccc3 |

All other experimental choices remain unchanged:

- Product implementation: 25d54050f87ba31357e37a414f437f02995729ac.
- Prime source: b71badc503f650cd7c10c4acd1206a8406aa0a0b.
- Runtime/manifest: 4BFA4A0500FECEAAEC737563623521562C5F4FDF2592EA443C956E0063A12579.
- Model openai-codex/gpt-5.4-mini, reasoning low, explicit empty MCP.
- Prompt: unchanged 123 UTF-8 bytes including terminal LF, SHA-256
  83DC86D01D9AC4B8137107154B4C94838E5AC8DC9F3C76A6E156A7ED036329C4.
- Expected answer remains blue after trimming; end_turn, existing no-tool,
  output-size and cleanup checks all remain mandatory.
- Existing runner, production launch/transport, admission, persistence paths,
  cancellation, retirement, evidence selection and sealing are unchanged.
- Operation 180s; initialization 60s; prompt 90s; cancellation 10s;
  retirement 60s; answer 64 UTF-8 bytes; evidence 16 files, 1 MiB/file, 4 MiB total.
- No provider output-token/subscription-usage ceiling is claimed. Returned usage
  is retained when available. Cancellation is not proof of immediate server stop.
- Same approved private PRIME_AGENT_CODING_AGENT_DIR; Prime alone may refresh.
  No login, credential inspection, copying, cleanup, or settings change.

Fresh roots are C:/UDEV/RookQualification/rookchat-prime-acp-slice-c-v2 and
the same path with -workspace; likewise v3 and v3-workspace. They must be absent
at admission. Session/root identifiers differ only to ensure independent fresh
sessions; neither arm resumes V1 or the other arm.

## Nonsecret observation immediately before each arm

Run the arm's existing --admit-only command, then the bounded observation below,
then its unchanged --execute command without intervening configuration changes.
Do not create a new observer service, product switch, or execution wrapper.
Use the same code for both arms; the only observation argument is its distinct
create-only diagnostic output path. Exact command literals and final protocol
hashes are supplied in the preparation review record after the commit.

The observation reads only the exact global settings.json and retains only
field presence/state, the derived image-permitting value and a UTC timestamp.
It does not load the private SettingsManager (which acquires locks), enumerate
credentials, dump settings, or hash/copy the entire settings file. Source-owned
checked_path supplies the existing regular/non-link path checks. Read size is
bounded to 64 KiB. Invalid/unreadable input is recorded generically and stops.
Both observations must derive false for blockImages. A true/unknown value stops
before contact, with no attempt to change it. A pre-run observation is not an
atomic capture of the later SDK read; this residual race remains disclosed.

Proposed PowerShell 7 observation body, used only after execution authorization:

```powershell
$observe = @'
import json, sys
from datetime import datetime, timezone
from pathlib import Path
repo = Path('C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset')
sys.path.insert(0, str(repo))
from scripts.qualification.rookchat_prime_acp_slice_c import checked_path
record = {'observedAtUtc': datetime.now(timezone.utc).isoformat(),
          'settingsFileExists': None, 'blockImagesState': 'unreadable',
          'effectiveBlockImages': None}
try:
    path = checked_path('C:/Users/bring/.prime-rook-slice-c-dev-auth-20260906-01/settings.json')
    record['settingsFileExists'] = path.exists()
    if not path.exists():
        record.update(blockImagesState='file_absent', effectiveBlockImages=False)
    else:
        path = checked_path(str(path), regular=True)
        with path.open('rb') as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise ValueError()
        data = json.loads(raw.decode('utf-8', 'strict'))
        if type(data) is not dict:
            raise ValueError()
        images = data.get('images')
        if images is not None and type(images) is not dict:
            raise ValueError()
        present = images is not None and 'blockImages' in images
        value = images.get('blockImages') if images is not None else None
        if value is not None and type(value) is not bool:
            raise ValueError()
        record.update(blockImagesState=('absent' if not present else 'null' if value is None else str(value).lower()),
                      effectiveBlockImages=False if value is None else value)
except Exception:
    record.update(blockImagesState='unreadable', effectiveBlockImages=None)
target = checked_path(sys.argv[1])
with target.open('xb') as output:
    output.write((json.dumps(record, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8'))
if record['effectiveBlockImages'] is not False:
    raise SystemExit('Image setting not admitted; stop without contact or repair.')
print('Nonsecret image setting observation retained; blockImages resolves false.')
'@
```

Observation files belong beside this experiment's ordinary review record, not
inside either create-only live evidence/workspace root or the auth directory.
Preserve them even if admission or a later arm refuses. A failed observation
does not authorize retry, configuration repair, or selection of another model.

## Frozen interpretation and stopping rules

After original v2 settles, inspect its sealed result. Proceed to v3 only if
the authorization covers both arms, stopReason is end_turn, cleanup.clean and
cleanup.child_exit_observed are true, cleanup.stderr_failure_code is null,
cancelAttempted and assistantAnswerOmitted are false, assistantAnswer is a
nonempty string of at most 64 UTF-8 bytes, and failure is null or
application_refused. Any known transport, protocol, tool, overflow or cleanup
fault stops the pair. A settled incorrect answer remains diagnostic data:
runner exit 1/application_refused does not, by itself, forbid the independently
bounded second arm. Do not retry v2, require it to pass, or tune v3.

This continuation rule does not turn application_refused into an answer-only
diagnosis. The unchanged runner aggregates answer mismatch, tool activity,
projection overflow and transport failure under that code; its sealed result
does not expose every predicate separately. Preserve this limitation. Continuing
to v3 does not certify those hidden predicates or waive either arm's verdict.
If a refusal cannot be distinguished from another application/transport fault,
report the pair as inconclusive rather than infer a size effect from the answers.

For interpreting the pair, both arms must have valid bounded application
observations and confirmed cleanup. Truncated/omitted output, other stop reasons,
transport/protocol/auth failure, deadlines or uncertain cleanup make the pair
inconclusive; stop and preserve it without filling the gap with another call.

| Original | Enlarged | Interpretation permitted |
| --- | --- | --- |
| blue | blue | Both samples answered correctly; V1 is still failed. No demonstrated fix or reliability claim. |
| not blue | blue | Consistent with the size hypothesis, but one ordered pair cannot establish causation or exclude randomness/time/context effects. |
| blue | not blue | No support for a size benefit in this pair; larger was not sufficient. No general regression claim. |
| not blue | not blue | Enlargement was not sufficient in this pair. Does not diagnose image dropping, blockImages, or model error. |

Report the exact observed answers, stop reasons, per-arm verdicts, cleanup and
available usage alongside the pre-run observations. Each run's original sealed
pass/fail result is retained unchanged. A v2/v3 pass is only that diagnostic
sample, not replacement of V1 or automatic completion of Slice C. Independent
review is required after the pair; no further slice or experiment is implied.
