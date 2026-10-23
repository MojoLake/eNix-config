#!/bin/bash
set -euo pipefail

source_dir=$1
policy=$2
build_dir=$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/focusguard-build.XXXXXX")
trap '/bin/rm -rf "$build_dir"' EXIT

echo 'Building FocusGuard for this Mac…'
/usr/bin/xcrun swiftc -O "$source_dir/Core.swift" "$source_dir/Learning.swift" "$source_dir/Runtime.swift" "$source_dir/Terminal.swift" "$source_dir/main.swift" -o "$build_dir/focusguard"
/usr/bin/codesign --force --sign - "$build_dir/focusguard"
echo 'Installing a root launch daemon and replacing mappings for the configured domains.'
echo 'Other hosts entries are preserved. The original hosts file is backed up.'
/usr/bin/sudo "$build_dir/focusguard" install "$policy"
