#!/bin/bash
#
# gen-fork-patches.sh - generate `git am`-able patches from the delta between a
# LineageOS-hosted repo and its WayDroid-ATV fork.
#
# Rationale
#
# Upstream WayDroid-ATV replaces frameworks/base, frameworks/av,
# frameworks/native, system/core, system/vold and hardware/interfaces with its
# own forks. We do not want that: it makes every LineageOS merge a manual merge.
#
# GitHub reports those forks as `status=ahead, behind_by=0` against
# LineageOS/lineage-23.2, i.e. the fork tip *contains* the LineageOS tip as an
# ancestor. So the merge-base is exactly the LineageOS tip, and the whole
# Waydroid delta is the commit range `LineageOS tip .. fork tip`.
#
# We therefore fetch only that range from the fork and `git format-patch` it.
# The result is an ordinary patch series that `git am` layers on top of the
# untouched LineageOS checkout.
#
# Usage:
#   gen-fork-patches.sh <lineageos-root> <out-dir> [project-path ...]
#
# With no project paths, every known project is generated.
set -euo pipefail

LOS_ROOT="${1:?usage: gen-fork-patches.sh <lineageos-root> <out-dir> [project...]}"
OUT_DIR="${2:?usage: gen-fork-patches.sh <lineageos-root> <out-dir> [project...]}"
shift 2

WORK="${GEN_WORKDIR:-$(mktemp -d)}"
mkdir -p "$WORK"

# project-path|fork-repo|fork-ref|expected-ahead
PROJECTS=(
  "frameworks/base|WayDroid-ATV/android_frameworks_base|lineage-23.2|22"
  "frameworks/av|WayDroid-ATV/android_frameworks_av|lineage-23.2|29"
  "frameworks/native|WayDroid-ATV/android_frameworks_native|lineage-23.2|26"
  "system/core|WayDroid-ATV/android_system_core|lineage-23.2|33"
  "system/vold|WayDroid-ATV/android_system_vold|lineage-23.2|8"
  "hardware/interfaces|WayDroid-ATV/android_hardware_interfaces|lineage-23.2|10"
  "lineage-sdk|WayDroid-ATV/android_lineage-sdk|lineage-23.2|12"
)

FETCH_DEPTH="${GEN_FETCH_DEPTH:-120}"

gen_one() {
  local proj="$1" fork="$2" ref="$3" want="$4"
  local losdir="$LOS_ROOT/$proj"
  local outdir="$OUT_DIR/$proj"
  local slot="$(echo "$proj" | tr '/' '_')"
  local bare="$WORK/$slot.git"

  if [[ ! -d "$losdir/.git" && ! -f "$losdir/.git" ]]; then
    echo "!! $proj: not present in LineageOS root, skipped"; return 0
  fi

  local los_tip
  los_tip="$(git -C "$losdir" rev-parse HEAD)"

  rm -rf "$bare"
  git init -q --bare "$bare"
  git -C "$bare" remote add fork "https://github.com/${fork}.git"

  echo "== $proj"
  echo "   LOS tip   : $los_tip"
  echo "   fork      : $fork@$ref"

  if ! git -C "$bare" \
        -c remote.fork.promisor=true \
        -c extensions.partialClone=fork \
        fetch -q --filter=blob:none --no-tags --depth="$FETCH_DEPTH" \
        fork "refs/heads/$ref:refs/remotes/fork/tip" 2>&1; then
    echo "!! $proj: fetch failed, skipped"; return 0
  fi

  # The merge-base is what we must diff against, so that the patch series
  # contains ONLY the Waydroid commits and never any LineageOS commit.
  #
  #   * clean case (status=ahead, behind_by=0): merge-base == LOS tip, so the
  #     series is exactly "LOS tip .. fork tip".
  #   * diverged case (e.g. lineage-sdk, behind_by=2): LineageOS has commits the
  #     fork never saw. Diffing from the merge-base still yields only the
  #     Waydroid commits; those LineageOS commits are already present in the
  #     checkout, and `git am -3` re-applies the Waydroid delta on top of them.
  local base
  base="$(git -C "$bare" merge-base "$los_tip" refs/remotes/fork/tip 2>/dev/null || true)"
  if [[ -z "$base" ]]; then
    echo "!! $proj: no merge-base within depth $FETCH_DEPTH (fetch too shallow). Skipped."
    echo "   re-run with GEN_FETCH_DEPTH=<n> $proj"
    return 0
  fi

  if [[ "$base" == "$los_tip" ]]; then
    echo "   merge-base: = LOS tip (fork is cleanly ahead)"
  else
    local behind
    behind="$(git -C "$bare" rev-list --count "$base".."$los_tip" 2>/dev/null || echo '?')"
    echo "   merge-base: ${base:0:12} (fork diverged; $behind LineageOS commit(s) not in fork)"
  fi

  local n
  n="$(git -C "$bare" rev-list --count "$base"..refs/remotes/fork/tip)"
  echo "   ahead     : $n commit(s) (compare API said $want)"
  if [[ "$n" != "$want" ]]; then
    echo "   note      : ahead-count differs from compare API; using local truth"
  fi

  rm -rf "$outdir"; mkdir -p "$outdir"
  git -C "$bare" format-patch -q --no-signature --zero-commit \
    "$base"..refs/remotes/fork/tip -o "$outdir" >/dev/null

  local cnt; cnt="$(find "$outdir" -name '*.patch' | wc -l)"
  local stat
  stat="$(git -C "$bare" diff --shortstat "$base"..refs/remotes/fork/tip 2>/dev/null || echo '?')"
  echo "   patches   : $cnt written -> ${outdir#"$OUT_DIR"/}"
  echo "   delta     : $stat"
}

selected=("$@")
if [[ ${#selected[@]} -eq 0 ]]; then
  selected=()
  for e in "${PROJECTS[@]}"; do selected+=("${e%%|*}"); done
fi

mkdir -p "$OUT_DIR"
for entry in "${PROJECTS[@]}"; do
  IFS='|' read -r p f r w <<< "$entry"
  for s in "${selected[@]}"; do
    if [[ "$p" == "$s" ]]; then gen_one "$p" "$f" "$r" "$w"; fi
  done
done
echo "OK: generation complete -> $OUT_DIR"
