#!/usr/bin/env bash
#
# Verify Proxmox backup archives and print one JSON object per archive.
#
# Read-only: it reads archives, computes checksums and validates their internal
# structure. It never writes to, moves, prunes or deletes an archive.
#
# Usage: verify-archives.sh /path/to/archive [...]
#
# A QEMU archive is verified by streaming it through `vma verify`. The exit
# status of the WHOLE pipeline matters — `zstdcat` succeeding while `vma verify`
# fails must not be reported as success — hence `set -o pipefail` plus an
# explicit PIPESTATUS check.

set -o errexit
set -o nounset
set -o pipefail

json_escape() {
    # Escape a string for embedding in JSON.
    printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e "s/$(printf '\t')/\\\\t/g" \
        | tr -d '\r' | awk 'BEGIN { ORS="" } { print (NR>1 ? "\\n" : "") $0 }'
}

emit() {
    local path="$1" ok="$2" method="$3" rc="$4" message="$5" size="$6" sum="$7" mtime="$8"
    printf '{"archive_path":"%s","ok":%s,"method":"%s","rc":%s,"message":"%s","size_bytes":%s,"sha256":"%s","mtime_epoch":%s}\n' \
        "$(json_escape "$path")" "$ok" "$(json_escape "$method")" "$rc" \
        "$(json_escape "$message")" "$size" "$sum" "$mtime"
}

verify_one() {
    local archive="$1"
    local size=0 sum="" mtime=0 rc=0 out="" method="" ok="false" verify_output=""

    if [ ! -f "$archive" ]; then
        emit "$archive" false "missing" 2 "archive does not exist" 0 "" 0
        return 0
    fi

    size=$(stat -c %s "$archive")
    mtime=$(stat -c %Y "$archive")
    sum=$(sha256sum "$archive" | awk '{print $1}')

    case "$archive" in
        *.vma.zst)
            method="zstdcat | vma verify -v -"
            verify_output=$(mktemp "${TMPDIR:-/tmp}/pve-archive-verify.XXXXXX")
            set +o errexit
            zstdcat "$archive" 2>>"$verify_output" | vma verify -v - >>"$verify_output" 2>&1
            local pipe_status=("${PIPESTATUS[@]}")
            set -o errexit
            out=$(tail -c 800 "$verify_output")
            rm -f -- "$verify_output"
            if [ "${pipe_status[0]}" -eq 0 ] && [ "${pipe_status[1]}" -eq 0 ]; then
                ok="true"
                rc=0
            else
                ok="false"
                rc="${pipe_status[1]}"
                [ "${pipe_status[0]}" -ne 0 ] && rc="${pipe_status[0]}"
            fi
            ;;
        *.vma)
            method="vma verify -v"
            set +o errexit
            out=$(vma verify -v "$archive" 2>&1)
            rc=$?
            set -o errexit
            [ "$rc" -eq 0 ] && ok="true"
            ;;
        *.tar.zst)
            method="zstd -t && tar --zstd -tf"
            set +o errexit
            out=$(zstd -t "$archive" 2>&1)
            rc=$?
            if [ "$rc" -eq 0 ]; then
                verify_output=$(mktemp "${TMPDIR:-/tmp}/pve-archive-list.XXXXXX")
                tar --zstd -tf "$archive" 2>&1 | tail -5 >"$verify_output"
                local tar_status=("${PIPESTATUS[@]}")
                rc="${tar_status[0]}"
                out="$out"$'\n'"$(cat "$verify_output")"
                rm -f -- "$verify_output"
            fi
            set -o errexit
            [ "$rc" -eq 0 ] && ok="true"
            ;;
        *)
            method="unsupported"
            rc=3
            out="unsupported archive extension"
            ;;
    esac

    emit "$archive" "$ok" "$method" "$rc" "$(printf '%s' "$out" | tail -c 800)" "$size" "$sum" "$mtime"
}

if [ "$#" -eq 0 ]; then
    echo "usage: $0 ARCHIVE [ARCHIVE...]" >&2
    exit 64
fi

for target in "$@"; do
    verify_one "$target"
done
