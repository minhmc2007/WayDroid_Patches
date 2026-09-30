# WayDroid ATV on LineageOS 23.2 — as patches, not forks

Target: **LineageOS 23.2 / SDK 36, phone build** (not Android TV).
Branch of this repo: `lineage-23.2`.

Upstream [WayDroid-ATV](https://github.com/WayDroid-ATV) gets its changes in by
`remove-project`ing roughly fifteen LineageOS projects from the manifest,
re-adding its own forks at the same paths, and then `git am`ing
`base-patches-36` on top of the fork. The result works, but every subsequent
LineageOS merge becomes a manual fork rebase, and it is impossible to see what
WayDroid actually changes relative to the ROM you started from.

This repo does the same job without replacing anything LineageOS maintains:

* Anything the LineageOS manifest already provides is **kept as the LineageOS
  checkout and patched**. `frameworks/base`, `frameworks/av`, `frameworks/native`,
  `hardware/interfaces`, `system/core`, `system/vold`, `lineage-sdk` and the rest
  are never removed from the manifest and never re-pointed at a fork.
* Only repos that **do not exist in LineageOS at all** are added to the manifest.
* The AOSP-remote display/media/rust projects that upstream swaps out are
  swapped here too, because the build genuinely does not link without them.

## Host requirements

Build host packages are **not** vendored here. Install them yourself:

```shell
sudo pacman -S --needed \
    bc bison flex gperf g++-multilib gcc-multilib git-lfs gnupg imagemagick \
    lzop pngcrush rsync schedtool squashfs-tools xsltproc zip \
    python-setuptools python-mako python-yaml \
    cbindgen \
    openjdk-17-jdk
```

Two of these are *not* in AOSP's documented list, because upstream's
`base-patches-36` does not list them either. Both fail the vendor image build
late, after several minutes of compiling, and the error names the missing
program rather than anything to do with WayDroid:

| package | error | why |
|---|---|---|
| `python-mako` | `ERROR: Problem encountered: Python (3.x) mako module >= 0.8.0 required to build mesa.` | mesa needs it to generate its glsl builtins |
| `cbindgen` | `src/nouveau/nil/meson.build:3:16: ERROR: Program 'cbindgen' not found or not executable` | nouveau's NIL driver needs it to bind Rust to C |

Note on the mako error: it is a *missing module*, not a Python version problem.
Any Python 3.x works once `mako` is importable, because mesa probes
`mako.__version__` and compares it against 0.8.0. The same error text appears
for both cases.

## Layout

    waydroid-patches.sh            the entry point
    manifest/
      00-remotes.xml               the ghub remote
      10-waydroid-projects.xml     pure addition, zero remove-project
      20-aosp-swaps.xml            the AOSP display/media swaps
    base-patches-36/
      10-lineage-forks/            generated fork deltas + our own build fixes
      20-upstream/                 upstream's hand-written base-patches-36
        roms-patches/              upstream conflict resolutions, used as fallback
    tools/
      gen-fork-patches.sh          regenerate the generated fork deltas
      track-upstream.py            how far the forks have moved (GitHub compare API)
      check-dup-modules.py         preflight for duplicate Soong module names
      xml-paths.py                 manifest fragment inspector
    TRACKING.md                    last tracking report

## Usage

```shell
# 1. add the manifest fragments and sync the extra projects
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
conflicted. It also syncs on its own, because several patches live in projects
that only exist because of our manifest.

`revert` and `apply` are a cheap on/off toggle: `revert` resets the patched
projects and drops the tags, but leaves the manifest and the added projects
alone, so re-applying needs no re-sync. Full teardown is explicit:

```shell
./waydroid-patches.sh revert <src> --yes --uninstall
./waydroid-patches.sh revert <src> --yes --purge-projects
```

The source directory may be relative or absolute; it is resolved before use.

## Options

```shell
-j <n>                parallelism for repo sync (default: nproc --all)
--no-sync             never run repo sync
--dry-run, -n         apply: report the verdict, change nothing
--layer <name>        apply: one layer only (10-lineage-forks | 20-upstream)
--only <project>      apply: repeatable, restrict to these projects
--no-aosp-swaps       manifest: strict pure-add manifest
--yes, -y             revert: actually do it
--uninstall           revert: also remove the manifest fragments
--purge-projects      revert: also delete the added project directories
```

## The two layers

`10-lineage-forks` is mostly generated. For each project that has a WayDroid
fork, `tools/gen-fork-patches.sh` fetches the fork and runs
`git format-patch merge-base..fork-tip`. Because the base is the merge-base and
not the LineageOS tip, the series contains **only** the WayDroid commits and
never a LineageOS commit. A diverged fork is handled too: `lineage-sdk` is 2
LineageOS commits behind its fork, and those two are left alone in the checkout.

The layer also holds our own hand-written build fixes, listed in
`docs/build-fixes.md`. Those exist because a few upstream projects have drifted
past what LineageOS 23.2 provides, and because upstream's `base-patches-36` was
authored against its own forks rather than against LineageOS trees that have
moved since.

`20-upstream` is upstream's `base-patches-36` vendored verbatim, minus the two
`vendor/intel/gmmlib` patches, plus the `roms-patches` fallbacks. The
`20-upstream` layer is applied **after** `10-lineage-forks`, because those
patches were written against the forks.

`packages/apps/TvSettings` is deliberately absent: the fork is 4 commits
*behind* LineageOS and has nothing we lack, and it is an ATV-only app that a
phone build does not use.

## Deviation from upstream: gmmlib

Upstream removes `platform/external/gmmlib` and adds `intel/gmmlib` at
`vendor/intel/gmmlib`. That duplicates the project, and both trees declare
`external_gmmlib_license`, `libigdgmm_android` and `libigdgmm_headers` with no
`soong_namespace`, so bootstrap fails:

```
error: external/gmmlib/Android.bp:25:1: module "external_gmmlib_license"
       already defined
```

LineageOS's own `external/gmmlib` is used instead, unpatched. Its two upstream
patches are both unnecessary there: `0002` adds x86 to an `arch` block that
already has it, and `0001` adds `GmmXe3P_XPCCachePolicy.cpp`, a file that only
exists in intel's `intel-gmmlib-22.10.0` snapshot.

`tools/check-dup-modules.py` is the preflight for this whole class of mistake.

## The AOSP swaps, and why `remove-project` is unavoidable there

`repo` gives a local manifest no way to point an existing project at a different
upstream repository:

* `<project path="X" .../>` is rejected as `duplicate path X`
  (`.repo/repo/manifest_xml.py`, `recursively_add_projects`).
* `<extend-project name="..." remote="..." revision="..."/>` is allowed, but it
  keeps the original project **name**, so the fetch URL becomes
  `<fetch>/platform/external/mesa3d` rather than the WayDroid fork.

So swapping `platform/external/mesa3d` for
`WayDroid-ATV/android_external_mesa3d` is only expressible as
`remove-project` + `project`, exactly as upstream does it. These seven are all
AOSP-remote display/media/rust trees that LineageOS does not maintain and no
custom ROM touches, and the build does not link without them: ffmpeg's 32-bit
variant needs `libva` for `android-x86`, and LineageOS's `external/libva` only
enables `x86_64`.

Because a swap replaces the local work tree, `manifest` runs
`repo sync --force-sync` scoped to exactly those seven **before** the normal
sync, since a plain `repo sync` also fails while those stale work trees are
present. `apply` re-applies the patches that force-sync discards.

Pass `--no-aosp-swaps` to install the strict pure-add manifest instead.

## Tracking upstream

```shell
python3 tools/track-upstream.py            # human readable, same output as TRACKING.md
python3 tools/track-upstream.py --regenerate
tools/gen-fork-patches.sh <los-root> "$PWD/base-patches-36/10-lineage-forks" frameworks/base
```

The GitHub compare API reports `ahead_by`/`behind_by` per fork. If `ahead` ever
stops matching the number of patches on disk, regenerate that project.

## Building

Not driven by this repo. In an envsetup'd shell:

```shell
lunch lineage_waydroid_x86_64-bp4a-userdebug
mka systemimage
mka vendorimage
```

Two environment caveats:

* `repo` keeps a JSON cache beside whatever gitconfig it reads. If your
  `~/.gitconfig` is newer than `~/.repo_.gitconfig.json`, `repo` tries to rewrite
  the cache, and soong mounts `$HOME` read-only for the build, so the
  `build-manifest.xml` rule dies with `Read-only file system`. Fix it by running
  `repo manifest -o /dev/null` once **outside** a build to refresh the cache.
* 15 GB of RAM is below what kati wants; it was `SIGKILL`ed at "finishing Make
  module rules". A large swap file helps but does not remove the need for RAM.

## Provenance

`20-upstream/` is a verbatim copy of `waydroid-patches/base-patches-36` and the
`roms-patches` fallbacks from
[WayDroid-ATV/android_vendor_waydroid](https://github.com/WayDroid-ATV/android_vendor_waydroid)
(branch `lineage-23.2`), which is licensed GPL-3.0. `10-lineage-forks/` is
generated from those same upstream commits and the hand-written fixes above, so
it inherits the same licence. See `LICENSE-NOTES.md`.
