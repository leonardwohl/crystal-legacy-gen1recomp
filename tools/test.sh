#!/usr/bin/env bash
# Rebuild the fixture, then run gen1recomp's mod checks and the load test.
#   tools/test.sh <gen1recomp checkout> <pokecrystal@base checkout>
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
engine="$(cd "${1:?gen1recomp checkout}" && pwd)"
base="$(cd "${2:?pokecrystal base checkout}" && pwd)"

python3 "$repo/tools/make_fixture.py" --base "$base" --out "$repo/tests/fixture_crystal.lua"
cd "$engine"
for check in validate lint gen2check; do
  python3 tools/modkit.py --repo "$engine" "$check" "$repo/mod"
done
luajit "$repo/tests/load_test.lua" "$repo"
