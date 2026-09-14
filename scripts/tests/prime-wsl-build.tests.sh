#!/usr/bin/env bash
set -euo pipefail

entry=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/build-prime-acp-runtime.sh
root=$(mktemp -d /tmp/rook-prime-build-test.XXXXXXXX)
trap 'rm -rf -- "$root"' EXIT
trap 'printf "HARNESS_ERROR: line %s\n" "$LINENO" >&2; exit 2' ERR
failures=0
if [[ ! -f $entry ]]; then
    printf 'RED build_entrypoint_missing\n'
    exit 1
fi

assert() { if ! "$@"; then printf 'ASSERTION: %s\n' "$*" >&2; return 1; fi; }
assert_not() { if "$@"; then printf 'UNEXPECTED: %s\n' "$*" >&2; return 1; fi; }
fixture() {
    case_root=$(mktemp -d "$root/case.XXXXXXXX")
    repo=$case_root/prime
    bin=$case_root/bin
    mkdir -p "$repo/scripts" "$bin"
    for tool in bash sh git dirname rm mkdir cp ls env sha256sum uname findmnt readlink head; do
        ln -s "$(command -v "$tool")" "$bin/$tool"
    done
    for tool in node npm bun zip unzip; do
        case $tool in node) version=v22.8.0;; npm) version=10.8.2;; bun) version=1.3.14;; *) version="$tool fixture 1";; esac
        printf '#!/bin/bash\nprintf "%%s\\n" %q\n' "$version" > "$bin/$tool"
        chmod +x "$bin/$tool"
    done
    cat > "$bin/timeout" <<'FAKE'
#!/bin/bash
set -eu
base=${BASH_SOURCE[0]%/bin/timeout}
printf '%s\n' "$@" > "$base/timeout.args"
[[ $1 == --kill-after=30s && $2 == 1800s ]] || exit 71
shift 2
exec "$@"
FAKE
    chmod +x "$bin/timeout"
    cat > "$repo/scripts/build-binaries.sh" <<'FAKE'
#!/bin/bash
set -eu
base=${PWD%/prime}
printf '%s\n' "$@" > "$base/builder.args"
env > "$base/builder.env"
printf 'synthetic builder stdout\n'
printf 'synthetic builder stderr\n' >&2
mode=success
[[ ! -f $base/mode ]] || read -r mode < "$base/mode"
mkdir -p packages/coding-agent/binaries
case $mode in
    dirty) printf 'changed\n' >> package-lock.json;;
    head) git -c user.name=Fixture -c user.email=fixture@example.invalid commit --allow-empty -m changed >/dev/null;;
    missing) exit 0;;
    link) ln -s "$PWD/package-lock.json" packages/coding-agent/binaries/pi-windows-x64.zip; exit 0;;
    directory) mkdir packages/coding-agent/binaries/pi-windows-x64.zip; exit 0;;
    timeout) exit 124;;
esac
printf 'synthetic upstream ZIP\n' > packages/coding-agent/binaries/pi-windows-x64.zip
FAKE
    chmod +x "$repo/scripts/build-binaries.sh"
    printf '{}\n' > "$repo/package-lock.json"
    printf '/packages/coding-agent/binaries/\n' > "$repo/.gitignore"
    git -C "$repo" init -q
    git -C "$repo" -c user.name=Fixture -c user.email=fixture@example.invalid commit --allow-empty -qm parent
    parent=$(git -C "$repo" rev-parse HEAD)
    git -C "$repo" add .
    git -C "$repo" -c user.name=Fixture -c user.email=fixture@example.invalid commit -qm fixture
    commit=$(git -C "$repo" rev-parse HEAD)
    record=$case_root/build.txt
}
invoke() {
    result=0
    env -i PATH="$bin:/usr/bin:/bin" HOME="$case_root" \
        OPENAI_API_KEY=not-a-secret PI_PACKAGE_DIR=/ambient PRIME_AGENT_KERNEL_PYTHON=/ambient \
        NPM_CONFIG_REGISTRY=https://invalid.example "${extra_env[@]}" \
        /bin/bash "$entry" --prime-worktree "$repo" --build-record "$record" \
        --expected-prime-commit "$commit" --expected-prime-parent "$parent" "$@" \
        > "$case_root/output" 2>&1 || result=$?
}
refused_before_build() { assert test "$result" -ne 0; assert test ! -e "$case_root/builder.args"; }
run_case() {
    local name=$1
    shift
    fixture
    extra_env=()
    local status=0
    set +e
    ( trap - ERR; set -e; "$@" )
    status=$?
    set -e
    if [[ $status == 0 ]]; then printf 'PASS %s\n' "$name"; else
        [[ $status == 1 ]] || { printf 'HARNESS_ERROR %s exit=%s\n' "$name" "$status"; exit 2; }
        printf 'FAIL %s\n' "$name"; cat "$case_root/output" 2>/dev/null || true
        failures=$((failures + 1))
    fi
}
success_case() {
    invoke
    assert test "$result" -eq 0
    assert test "$(cat "$case_root/builder.args")" = "$(printf '%s\n' --platform windows-x64 --frozen-model-catalog)"
    assert test "$(cat "$case_root/timeout.args")" = "$(printf '%s\n' --kill-after=30s 1800s ./scripts/build-binaries.sh --platform windows-x64 --frozen-model-catalog)"
    assert test -f "$case_root/build-console.log"
    assert grep -q -F 'synthetic builder stdout' "$case_root/build-console.log"
    assert grep -q -F 'synthetic builder stderr' "$case_root/build-console.log"
    local keys
    keys=$(cut -d= -f1 "$case_root/builder.env" | LC_ALL=C sort)
    assert test "$keys" = "$(printf '%s\n' CI HOME LANG LC_ALL PATH PWD SHLVL TMPDIR _ | LC_ALL=C sort)"
    local zip_hash
    zip_hash=$(sha256sum "$repo/packages/coding-agent/binaries/pi-windows-x64.zip")
    assert grep -F "${zip_hash%% *}" "$record"
    for key in outcome=success started= finished= node=v22.8.0 npm=10.8.2 bun=1.3.14 git= zip= unzip= command=; do
        assert grep -q -F "$key" "$record"
    done
    local path_value home_value tmp_value
    path_value=$(sed -n 's/^PATH=//p' "$case_root/builder.env")
    assert test "$path_value" = "$bin"
    home_value=$(sed -n 's/^HOME=//p' "$case_root/builder.env")
    tmp_value=$(sed -n 's/^TMPDIR=//p' "$case_root/builder.env")
    assert test "${home_value%/home}" = "${tmp_value%/tmp}"
    assert test "${home_value#"$repo"}" = "$home_value"
}
invalid_args() { invoke --extra nope; refused_before_build; }
utc_record_case() {
    extra_env=(TZ=EST5)
    assert test "$(TZ=EST5 date +%z)" = -0500
    local before after key stamp epoch
    before=$(date +%s)
    invoke
    after=$(date +%s)
    assert test "$result" -eq 0
    for key in started finished; do
        stamp=$(sed -n "s/^$key=//p" "$record")
        assert test "${stamp: -1}" = Z
        epoch=$(date -u -d "$stamp" +%s)
        assert test "$epoch" -ge "$before"
        assert test "$epoch" -le "$after"
    done
}
missing_args() {
    result=0
    env -i PATH="$bin" /bin/bash "$entry" --prime-worktree "$repo" > "$case_root/output" 2>&1 || result=$?
    refused_before_build
}
bad_commit() { commit=not-a-commit; invoke; refused_before_build; }
wrong_commit() { commit=$parent; invoke; refused_before_build; }
dirty_case() { printf x >> "$repo/package-lock.json"; invoke; refused_before_build; }
hosted_case() { repo=$1; invoke; refused_before_build; }
filesystem_case() {
    rm "$bin/findmnt"
    printf '#!/bin/bash\nprintf "%%s\\n" %q\n' "$1" > "$bin/findmnt"
    chmod +x "$bin/findmnt"
    invoke; refused_before_build
}
missing_tool() {
    rm "$bin/$1"
    # No fallback path: all admitted tools except the deliberately missing one are local.
    extra_env=(PATH="$bin")
    invoke; refused_before_build
}
bad_node() { printf '#!/bin/bash\necho v22.7.9\n' > "$bin/node"; invoke; refused_before_build; }
bad_bun() { printf '#!/bin/bash\necho 1.3.15\n' > "$bin/bun"; invoke; refused_before_build; }
post_build() {
    printf '%s\n' "$1" > "$case_root/mode"
    invoke
    assert test "$result" -ne 0
    assert test -e "$case_root/builder.args"
    if [[ -f $record ]]; then assert_not grep -q 'outcome=success' "$record"; fi
}
existing_output() { mkdir -p "$repo/packages/coding-agent/binaries"; invoke; refused_before_build; }
existing_record() { printf 'preserve\n' > "$record"; invoke; refused_before_build; assert test "$(cat "$record")" = preserve; }
existing_console() {
    printf 'preserve\n' > "$case_root/build-console.log"
    invoke
    refused_before_build
    assert test "$(cat "$case_root/build-console.log")" = preserve
}
network_case() {
    extra_env=(HTTP_PROXY=https://redacted.example HTTPS_PROXY=https://redacted.example ALL_PROXY=https://redacted.example NO_PROXY=localhost)
    invoke; assert test "$result" -eq 0
    for key in HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY; do assert grep -q "^$key=" "$case_root/builder.env"; done
    assert_not grep -q redacted "$record"
}
network_refusal() { extra_env=("$1=https://invalid.example"); invoke; refused_before_build; }
changed_version() {
    printf '#!/bin/bash\nbase=%q\nif [[ -e $base/probed ]]; then echo %q; else : > "$base/probed"; echo %q; fi\n' \
        "$case_root" "$2" "$3" > "$bin/$1"
    invoke; refused_before_build
}
precedence_case() {
    mkdir "$case_root/first"
    printf '#!/bin/bash\necho 1.3.14\n' > "$case_root/first/bun"
    chmod +x "$case_root/first/bun"
    extra_env=(PATH="$case_root/first:$bin:/usr/bin:/bin")
    invoke; assert test "$result" -eq 0
    assert grep -q "^PATH=$case_root/first:$bin$" "$case_root/builder.env"
}
changed_tool_target() {
    printf '#!/bin/bash\n/usr/bin/ln -sf /usr/bin/ls %q\necho v22.8.0\n' "$bin/cp" > "$bin/node"
    invoke; refused_before_build
}
changed_tool_path() {
    mkdir "$case_root/first"
    printf '#!/bin/bash\necho 1.3.14\n' > "$case_root/first/bun"
    chmod +x "$case_root/first/bun"
    printf '#!/bin/bash\n/usr/bin/ln -sf /usr/bin/cp %q\necho v22.8.0\n' "$case_root/first/cp" > "$bin/node"
    extra_env=(PATH="$case_root/first:$bin:/usr/bin:/bin")
    invoke; refused_before_build
}

run_case complete_public_handoff success_case
run_case non_utc_caller_records_actual_utc utc_record_case
run_case extra_argument_refusal invalid_args
run_case missing_argument_refusal missing_args
run_case malformed_commit_refusal bad_commit
run_case wrong_commit_refusal wrong_commit
run_case dirty_source_refusal dirty_case
run_case c_drive_refusal hosted_case /mnt/c/source
run_case d_drive_refusal hosted_case /mnt/d/source
for fs in drvfs 9p ntfs fuseblk; do run_case "${fs}_refusal" filesystem_case "$fs"; done
for tool in uname findmnt readlink head; do run_case "missing_${tool}" missing_tool "$tool"; done
run_case minimum_node bad_node
run_case qualified_bun bad_bun
for mode in dirty head missing link directory timeout; do run_case "post_build_${mode}" post_build "$mode"; done
run_case old_output_refusal existing_output
run_case record_create_only existing_record
run_case console_create_only existing_console
run_case explicit_network_names network_case
for name in http_proxy Http_Proxy FTP_PROXY; do run_case "unapproved_${name}" network_refusal "$name"; done
run_case final_node_version changed_version node v23.0.0 v22.8.0
run_case final_bun_version changed_version bun 1.3.15 1.3.14
run_case original_path_precedence precedence_case
run_case final_command_target changed_tool_target
run_case final_command_path changed_tool_path
printf 'BUILD_ENTRYPOINT_FAILURES=%s\n' "$failures"
if [[ $failures != 0 ]]; then exit 1; fi
