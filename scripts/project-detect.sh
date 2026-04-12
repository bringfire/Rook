#!/usr/bin/env bash
# Rook Plugin — Project detection hook (sourced by session-start.sh)
# Checks whether the current working directory has Rook context in CLAUDE.md.
# Returns a suggestion string if Rook context is missing, empty string otherwise.

detect_project_setup() {
    local claude_md="CLAUDE.md"
    local suggestion=""

    # --- Skip: Rook source repo (walk up to git root) ---
    local git_root
    if git_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
        if [ -f "$git_root/mcp_server/src/rook/server.py" ] || \
           [ -f "$git_root/src/RookNative/RookServer.cpp" ]; then
            printf ''
            return
        fi
    fi

    # --- Skip: %LOCALAPPDATA%/Rook (the runtime/install root) ---
    # Use cygpath for consistent POSIX paths in Git Bash on Windows.
    # On non-Windows (no cygpath), fall back to tr-based normalization.
    local normalized_cwd normalized_install
    local localappdata="${LOCALAPPDATA:-}"

    if [ -n "$localappdata" ]; then
        if command -v cygpath >/dev/null 2>&1; then
            normalized_cwd="$(cygpath -u "$(pwd)" | tr '[:upper:]' '[:lower:]')"
            normalized_install="$(cygpath -u "$localappdata/Rook" | tr '[:upper:]' '[:lower:]')"
        else
            normalized_cwd="$(pwd | tr '\\' '/' | tr '[:upper:]' '[:lower:]')"
            normalized_install="$(echo "$localappdata/Rook" | tr '\\' '/' | tr '[:upper:]' '[:lower:]')"
        fi
        if [[ "$normalized_cwd/" == "$normalized_install/"* ]]; then
            printf ''
            return
        fi
    fi

    if [ -f "$claude_md" ]; then
        # CLAUDE.md exists — check for Rook marker
        if grep -q 'rhino_execute_intent\|gh_execute_intent\|rhino_ping' "$claude_md" 2>/dev/null; then
            # Rook context already present
            printf ''
            return
        else
            # CLAUDE.md exists but no Rook context
            suggestion="This project has a CLAUDE.md but no Rook context. Run /project-setup to add Rook tools and project-specific configuration."
        fi
    else
        # No CLAUDE.md at all — check if this looks like a Rhino/GH project
        local has_project_files=false
        for ext in 3dm gh ghx; do
            if ls ./*."$ext" 1>/dev/null 2>&1; then
                has_project_files=true
                break
            fi
        done

        if [ "$has_project_files" = true ]; then
            suggestion="This folder contains Rhino/Grasshopper files but no CLAUDE.md. Run /project-setup to configure Rook for this project."
        else
            suggestion="No CLAUDE.md found in this directory. If this is a Rhino/GH project, run /project-setup to configure Rook."
        fi
    fi

    printf '%s' "$suggestion"
}
