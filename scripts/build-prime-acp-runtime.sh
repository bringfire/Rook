#!/usr/bin/env bash
set -euo pipefail

readonly EXPECTED_BUN_VERSION=1.3.14 MINIMUM_NODE_VERSION=22.8.0
readonly BUILD_TIMEOUT_SECONDS=1800 BUILD_KILL_AFTER_SECONDS=30
refuse() { printf 'build_refused: %s\n' "$*" >&2; exit 1; }
declare -A args=()
while (( $# )); do
    [[ $# -ge 2 ]] || refuse 'missing argument value'
    case $1 in --prime-worktree|--build-record|--expected-prime-commit|--expected-prime-parent) ;;
        *) refuse 'unknown argument';; esac
    [[ ! -v args[$1] && -n $2 ]] || refuse 'duplicate or empty argument'
    args[$1]=$2
    shift 2
done
[[ ${#args[@]} == 4 ]] || refuse 'four explicit arguments required'
expected=${args[--expected-prime-commit]}
parent=${args[--expected-prime-parent]}
[[ $expected =~ ^[0-9a-f]{40}$ && $parent =~ ^[0-9a-f]{40}$ ]] || refuse 'invalid Git identity'
[[ ${args[--prime-worktree]} != /mnt/* ]] || refuse 'Windows-hosted build root'
[[ -f /etc/os-release ]] || refuse 'Ubuntu 24.04 required'
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 ]] || refuse 'Ubuntu 24.04 required'

required=(bash sh node npm bun git zip unzip dirname rm mkdir cp ls env timeout sha256sum uname findmnt readlink head)
declare -A commands=() targets=() directories=()
for tool in "${required[@]}"; do
    commands[$tool]=$(type -P "$tool") || refuse "missing prerequisite: $tool"
done
native_path() {
    local path=$1 fs
    [[ $path == /* && $path != /mnt/* && -f $path && -x $path ]] || return 1
    fs=$("${commands[findmnt]}" -n -o FSTYPE -T "$path") || return 1
    case ${fs,,} in ''|drvfs|9p|ntfs|ntfs3|fuseblk) return 1;; esac
}
for tool in "${required[@]}"; do
    path=${commands[$tool]}
    native_path "$path" || refuse "non-native command: $tool"
    target=$("${commands[readlink]}" -f -- "$path") || refuse "unresolved command: $tool"
    native_path "$target" || refuse "non-native command target: $tool"
    targets[$tool]=$target
    directories[${path%/*}]=1
done
[[ $("${commands[uname]}" -s) == Linux ]] || refuse 'Linux required'
linux_build_path=
IFS=: read -r -a input_directories <<< "$PATH"
declare -A admitted=()
for directory in "${input_directories[@]}"; do
    if [[ -v directories[$directory] && ! -v admitted[$directory] ]]; then
        linux_build_path+=${linux_build_path:+:}$directory
        admitted[$directory]=1
    fi
done
worktree=$("${commands[readlink]}" -f -- "${args[--prime-worktree]}") || refuse 'invalid worktree'
[[ -d $worktree && $worktree != /mnt/* ]] || refuse 'invalid worktree'
fs=$("${commands[findmnt]}" -n -o FSTYPE -T "$worktree")
case ${fs,,} in ''|drvfs|9p|ntfs|ntfs3|fuseblk) refuse 'Windows-hosted worktree';; esac
record=${args[--build-record]}
record_parent=$("${commands[readlink]}" -f -- "$("${commands[dirname]}" -- "$record")") || refuse 'invalid record parent'
[[ -d $record_parent && $record_parent != /mnt/* ]] || refuse 'non-native record parent'
record=$record_parent/${record##*/}
[[ ! -e $record && ! -L $record && $record != "$worktree"/* ]] || refuse 'record must be new and outside source'
console=$record_parent/build-console.log
[[ ! -e $console && ! -L $console ]] || refuse 'build console must be new'

# Only explicitly supplied uppercase proxy names may survive the caller's clean environment.
network=()
network_names=()
while IFS= read -r name; do
    case ${name,,} in *_proxy|proxy)
        case $name in HTTP_PROXY|HTTPS_PROXY|ALL_PROXY|NO_PROXY)
            network+=("$name=${!name}"); network_names+=("$name");;
            *) refuse 'unapproved network environment name';;
        esac;;
    esac
done < <(compgen -e)

IFS= read -r generation < /proc/sys/kernel/random/uuid
support=${worktree%/*}/.prime-build-$generation
[[ ! -e $support && ! -L $support ]] || refuse 'support generation exists'
"${commands[mkdir]}" -- "$support"
"${commands[mkdir]}" -- "$support/home" "$support/tmp"
clean=("${commands[env]}" -i "HOME=$support/home" "PATH=$linux_build_path" LANG=C.UTF-8 LC_ALL=C.UTF-8 "TMPDIR=$support/tmp" CI=1 "${network[@]}")
node_version=$("${clean[@]}" "${commands[node]}" --version)
bun_version=$("${clean[@]}" "${commands[bun]}" --version)
valid_node() {
    [[ $1 =~ ^v([0-9]+)\.([0-9]+)\.([0-9]+)$ ]] || return 1
    (( BASH_REMATCH[1] > 22 || (BASH_REMATCH[1] == 22 && BASH_REMATCH[2] >= 8) ))
}
valid_node "$node_version" || refuse "Node $MINIMUM_NODE_VERSION or later required"
[[ $bun_version == "$EXPECTED_BUN_VERSION" ]] || refuse 'unqualified Bun version'
npm_version=$("${clean[@]}" "${commands[npm]}" --version)
git_version=$("${clean[@]}" "${commands[git]}" --version)
zip_version=$("${clean[@]}" "${commands[zip]}" -v)
unzip_version=$("${clean[@]}" "${commands[unzip]}" -v)
git_source() { "${clean[@]}" "${commands[git]}" -C "$worktree" "$@"; }
source_valid() {
    [[ $(git_source rev-parse HEAD) == "$expected" && $(git_source rev-parse HEAD^) == "$parent" ]] || return 1
    [[ -z $(git_source status --porcelain --untracked-files=no) ]] || return 1
    [[ -f $worktree/package-lock.json && ! -L $worktree/package-lock.json ]]
}
source_valid || refuse 'source identity or tracked cleanliness mismatch'
output=$worktree/packages/coding-agent/binaries
[[ ! -e $output && ! -L $output ]] || refuse 'existing build output'
lock_hash=$("${commands[sha256sum]}" -- "$worktree/package-lock.json")
lock_hash=${lock_hash%% *}
[[ -f $worktree/scripts/build-binaries.sh && ! -L $worktree/scripts/build-binaries.sh && -x $worktree/scripts/build-binaries.sh ]] || refuse 'missing upstream builder'
probe_args=()
for tool in "${required[@]}"; do probe_args+=("$tool" "${commands[$tool]}" "${targets[$tool]}"); done
printf -v started '%(%Y-%m-%dT%H:%M:%SZ)T' -1
result=0
(
    set -o noclobber
    : > "$console"
) || refuse 'build console publication failed'
(
    cd -- "$worktree"
    "${clean[@]}" "${commands[bash]}" --noprofile --norc -c '
        set -eu
        node_version=$1; bun_version=$2; shift 2
        while (( $# )); do
            [[ $(type -P "$1") == "$2" && $(readlink -f -- "$2") == "$3" ]] || exit 72
            shift 3
        done
        [[ $(node --version) == "$node_version" && $(bun --version) == "$bun_version" ]] || exit 73
        exec timeout --kill-after=30s 1800s ./scripts/build-binaries.sh --platform windows-x64 --frozen-model-catalog
    ' build "$node_version" "$bun_version" "${probe_args[@]}"
) > "$console" 2>&1 || result=$?
while IFS= read -r line || [[ -n $line ]]; do printf '%s\n' "$line"; done < "$console"
printf -v finished '%(%Y-%m-%dT%H:%M:%SZ)T' -1
outcome=failed
zip_hash=
if [[ $result == 0 ]] && source_valid; then
    after_hash=$("${commands[sha256sum]}" -- "$worktree/package-lock.json")
    zip=$output/pi-windows-x64.zip
    if [[ ${after_hash%% *} == "$lock_hash" && -f $zip && ! -L $zip ]]; then
        zip_hash=$("${commands[sha256sum]}" -- "$zip")
        zip_hash=${zip_hash%% *}
        outcome=success
    fi
fi
(
    set -o noclobber
    printf 'outcome=%s\nstarted=%s\nfinished=%s\ncommand=timeout --kill-after=30s 1800s ./scripts/build-binaries.sh --platform windows-x64 --frozen-model-catalog\nconsole=build-console.log\nprime=%s\nparent=%s\nlockfile=%s\nnode=%s\nnpm=%s\nbun=%s\ngit=%s\nzip=%s\nunzip=%s\nnetwork_names=%s\nzip_sha256=%s\nexit_code=%s\n' \
        "$outcome" "$started" "$finished" "$expected" "$parent" "$lock_hash" \
        "${node_version:0:1024}" "${npm_version:0:1024}" "${bun_version:0:1024}" "${git_version:0:1024}" \
        "${zip_version:0:1024}" "${unzip_version:0:1024}" "${network_names[*]}" "$zip_hash" "$result" > "$record"
) || refuse 'build record publication failed'
[[ $outcome == success ]] || refuse "build or post-build custody failed (exit $result)"
printf 'build_accepted: %s\n' "$zip"
