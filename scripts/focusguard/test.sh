#!/bin/bash
set -euo pipefail
source_dir=$(cd "$(dirname "$0")" && pwd)
build_dir=$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/focusguard-tests.XXXXXX")
trap '/bin/rm -rf "$build_dir"' EXIT
/usr/bin/xcrun swiftc "$source_dir/Core.swift" "$source_dir/Learning.swift" "$source_dir/Runtime.swift" "$source_dir/tests.swift" -o "$build_dir/tests"
"$build_dir/tests" "$source_dir/passages.json"
/usr/bin/xcrun swiftc "$source_dir/Core.swift" "$source_dir/Learning.swift" "$source_dir/Terminal.swift" "$source_dir/terminal-tests.swift" -o "$build_dir/terminal-tests"
/usr/bin/python3 "$source_dir/test-terminal.py" "$build_dir/terminal-tests" "$source_dir/passages.json"
/usr/bin/xcrun swiftc -O "$source_dir/Core.swift" "$source_dir/Learning.swift" "$source_dir/Runtime.swift" "$source_dir/Terminal.swift" "$source_dir/main.swift" -o "$build_dir/focusguard"
"$build_dir/focusguard" help
/usr/bin/file "$build_dir/focusguard"
