# WayDroid ATV on LineageOS 23.2 — as patches, not forks

Target: **LineageOS 23.2 / SDK 36, phone build** (not Android TV).
Branch of this repo: `lineage-23.2`.

Upstream [WayDroid-ATV](https://github.com/WayDroid-ATV) gets its changes in by
`remove-project`ing roughly fifteen LineageOS projects from the manifest,
re-adding its own forks at the same paths, and then `git am`ing
`base-patches-36` on top of the fork. The result works, but every subsequent
LineageOS merge becomes a manual fork rebase, and it is impossible to see what
WayDroid actually changes relative to the ROM you started from.

This repo does the same job without replacing anything:

* Anything the LineageOS manifest already provides is **kept as the LineageOS
  checkout and patched**. `frameworks/base`, `frameworks/av`, `frameworks/native`,
  `hardware/interfaces`, `system/core`, `system/vold`, `lineage-sdk` and the rest
  are never removed from the manifest and never re-pointed at a fork.
* Only repos that **do not exist in LineageOS at all** are added to the manifest.
* The handful of AOSP-remote display/media/rust projects that upstream swaps out
  are opt-in, and are the only place a `remove-project` can appear.

## Layout

    waydroid-patches.sh            the entry point
    manifest/
      00-remotes.xml               the ghub remote
      10-waydroid-projects.xml     pure addition, 21 projects, zero remove-project
      20-aosp-swaps.xml            opt-in AOSP swaps, the only remove-project
    base-patches-36/
      10-lineage-forks/            generated: the WayDroid fork deltas
      20-upstream/                 vendored: upstream's hand-written base-patches-36
        roms-patches/              upstream conflict resolutions, used as a fallback
    tools/
      gen-fork-patches.sh          regenerate 10-lineage-forks
      track-upstream.py            how far the forks have moved (GitHub compare API)
      xml-paths.py                 manifest fragment inspector
    TRACKING.md                    last tracking report

## Usage

```shell
# 1. add the manifest fragments and sync the 21 extra projects
./waydroid-patches.sh manifest /path/to/LineageOS

# 2. layer the patches (syncs first if the added projects are missing)
./waydroid-patches.sh apply /path/to/LineageOS

# check state
./waydroid-patches.sh status /path/to/LineageOS

# undo everything: patches, manifest fragments, added project dirs
./waydroid-patches.sh revert /path/to/LineageOS          # plan only
./waydroid-patches.sh revert /path/to/LineageOS --yes    # do it
```

`apply` is idempotent, so it is safe to re-run after a `repo sync`. It reports
each patch as `applied`, `already` or `conflict`, and exits non-zero if anything
conflicted. It also syncs on its own: several patches live in projects that only
exist because of our manifest (`external/llvm-project`, `vendor/intel/*`), and it
runs `repo sync -c -j$(nproc --all)` when any of them is missing from the tree.

The source directory may be relative or absolute; it is resolved before use.

## Options

```shell
-j <n>                parallelism for repo sync (default: nproc --all)
--no-sync             never run repo sync
--dry-run, -n         apply: report the verdict, change nothing
--layer <name>        apply: one layer only (10-lineage-forks | 20-upstream)
--only <project>      apply: repeatable, restrict to these projects
--with-aosp-swaps     manifest: also install the 7 remove-project AOSP swaps
--yes, -y             revert: actually do it
--keep-manifest       revert: keep the local_manifests fragments
--keep-projects       revert: keep the added project directories
```

## The two layers

`10-lineage-forks` is generated, not hand-written. For each project that has a
WayDroid fork, `tools/gen-fork-patches.sh` fetches the fork and runs
`git format-patch merge-base..fork-tip`. Because the base is the merge-base and
not the LineageOS tip, the resulting series contains **only** the WayDroid
commits and never a LineageOS commit. This also means a fork that has diverged
is handled: `lineage-sdk` is 2 LineageOS commits behind its fork, and those two
commits are simply left alone in the checkout.

The current forks sit cleanly ahead of `lineage-23.2`, so the deltas are small:

| project | commits | files |
|---|---|---|
| frameworks/av | 29 | 56 |
| frameworks/base | 22 | 35 |
| frameworks/native | 26 | 53 |
| system/core | 33 | 25 |
| hardware/interfaces | 10 | 15 |
| lineage-sdk | 12 | 20 |
| system/vold | 8 | 6 |

`20-upstream` is upstream's `base-patches-36` vendored verbatim, plus the
`roms-patches` fallbacks. These carry the hand-written WayDroid behaviour (SELinux
relaxations, vold and linkerconfig fixes, lmkd, bionic text relocations) and were
written against the forks, so they are applied **after** `10-lineage-forks`.

`10-lineage-forks` also carries a small number of hand-written compatibility
patches that are not fork deltas, currently just `external/rust/hbm`: its
`refs/heads/main` has drifted to referencing `libash_latest_rust`, which no
project in a 23.2 tree defines, so the patch renames it to the `libash_rust`
that android-crates-io actually provides.

`packages/apps/TvSettings` is deliberately absent from both layers: the fork is
4 commits *behind* LineageOS and has nothing we lack, and it is an ATV-only app
that a phone build does not use.

## The AOSP swaps, and why `remove-project` is unavoidable there

`repo` gives a local manifest no way to point an existing project at a different
upstream repository:

* `<project path="X" .../>` is rejected as `duplicate path X`
  (`.repo/repo/manifest_xml.py`, `recursively_add_projects`).
* `<extend-project name="..." remote="..." revision="..."/>` is allowed, but it
  keeps the original project **name**, so the fetch URL becomes
  `<fetch>/platform/external/mesa3d` rather than the WayDroid fork.

So swapping `platform/external/mesa3d` for `WayDroid-ATV/android_external_mesa3d`
is only expressible as `remove-project` + `project`, exactly as upstream does it.
These seven are all AOSP-remote display/media/rust trees that LineageOS does not
maintain and no custom ROM touches, so they are quarantined in
`manifest/20-aosp-swaps.xml` and only installed on request:

They are installed by default, because the build genuinely needs them: ffmpeg's
32-bit variant requires `libva` for `android-x86`, and LineageOS's
`external/libva` only enables `x86_64`, so without the swap kati fails with
`libavcodec (SHARED_LIBRARIES android-x86) missing libva`. Pass
`--no-aosp-swaps` to install the strict pure-add manifest instead.

Swapping replaces the local work tree of those projects, so `manifest` runs
`repo sync --force-sync` scoped to exactly those seven before the normal sync.
That discards the patches on them, so re-run `apply` afterwards.

`external/rust/android-crates-io` is also left as the LineageOS copy. LineageOS
already pins the `android-16.0.0_r4` tag, which is what SDK 36 wants, and a
commented-out swap is left in `20-aosp-swaps.xml` for the day a build needs it.

## Tracking upstream

```shell
python3 tools/track-upstream.py            # human readable, same output as TRACKING.md
python3 tools/track-upstream.py --regenerate
```

The GitHub compare API reports `ahead_by`/`behind_by` per fork. If `ahead` ever
stops matching the number of patches on disk, regenerate that project:

```shell
tools/gen-fork-patches.sh /path/to/LineageOS "$PWD/base-patches-36/10-lineage-forks" frameworks/base
```

## Provenance

`20-upstream/` is a verbatim copy of `waydroid-patches/base-patches-36` and
`roms-patches` from [WayDroid-ATV/android_vendor_waydroid](https://github.com/WayDroid-ATV/android_vendor_waydroid)
(branch `lineage-23.2`), which is licensed GPL-3.0. `10-lineage-forks/` is
generated from those same upstream commits, so it inherits the same licence.
