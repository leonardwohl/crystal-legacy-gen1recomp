#!/usr/bin/env bash
# Rebuild the fixture, run gen1recomp's modkit checks on every mod, then load
# each mod alone and all of them together through gen1recomp's real loader.
#   tools/test.sh <gen1recomp checkout> <pokecrystal@82e315e48 checkout>
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
engine="$(cd "${1:?gen1recomp checkout}" && pwd)"
base="$(cd "${2:?pokecrystal base checkout}" && pwd)"

python3 "$repo/tools/make_fixture.py" --base "$base" --out "$repo/tests/fixture_crystal.lua"
mods=()
for dir in "$repo"/mods/*/; do mods+=("$(basename "$dir")"); done

cd "$engine"
status=0
for id in "${mods[@]}"; do
  for check in validate lint gen2check; do
    python3 tools/modkit.py --repo "$engine" --quiet "$check" "$repo/mods/$id" || status=1
  done
  luajit "$repo/tests/load_test.lua" "$repo" "$id" | grep -v '^\[info\]' || status=1
done
echo "== all mods together"
luajit "$repo/tests/load_test.lua" "$repo" "${mods[@]}" | grep -v '^\[info\]' || status=1

# Optional: real importer output for each ROM revision you have dumped with
# tools/extract_real.lua, e.g. CL_REAL="dumps/crystal10 dumps/crystal11".
for dump in ${CL_REAL:-}; do
  echo "== real data: $dump"
  for id in "${mods[@]}"; do
    CL_FIXTURE="$dump" luajit "$repo/tests/load_test.lua" "$repo" "$id" | grep -v '^\[info\]' || status=1
  done
  CL_FIXTURE="$dump" luajit "$repo/tests/load_test.lua" "$repo" "${mods[@]}" | grep -v '^\[info\]' || status=1
done
exit $status
