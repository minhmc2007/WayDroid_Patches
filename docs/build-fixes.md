# Build fixes in `15-ours`

These live in layer `15-ours`, under Apache-2.0, deliberately kept apart from
the GPL-3.0 fork deltas. They are hand-written patches against projects that
have drifted past what LineageOS 22.2 provides, or that ship without a
LineageOS-side fix.

Each one was made only after a build failed, and each commit message quotes the
actual error.

| patch | project | why |
|---|---|---|
| `vendor/gapps/0001` | drop `apps` on `prebuilt_apex` | Android 15's Soong has no such property |
| `external/libsndfile/0001` | `libsndfile_linux` → `libsndfile12` | upstream's own pulseaudio depends on `libsndfile12` |

Both are inconsistencies in upstream's `manifests-35` rather than defects we
introduced. On Android 16 neither showed up, which is why upstream never fixed
them.

## The gapps one

```
error: vendor/gapps/x86_64/Android.bp:90:9: unrecognized property "apps"
```

`apps` on `prebuilt_apex` is newer than the Soong in Android 15. Upstream 22.2
pins `android_vendor_gapps@cinnamonbun`, whose head is `74fba8f` "Reland x86_64
support" (2026-07-07), written against a Soong that has the property. That is
the only commit on `cinnamonbun` that touches `x86_64/Android.bp`, so there is
no older revision of the branch to pin instead.

The property only associates the apex with `PrebuiltGmsCoreVic`, which is defined
in `vendor/gapps/dummy-apps/Android.bp`. Dropping it leaves the apex building
and installing, which is all a phone build needs. The same three lines are
dropped from `arm/Android.bp` and `arm64/Android.bp`.

## The libsndfile one

```
error: external/pulseaudio/src/Android.bp:82:1: "libpulse" depends on
undefined module "libsndfile12".
Or did you mean ["libsndfile"]?
```

Upstream 22.2 pins `external/pulseaudio` and `external/libsndfile` both at
`lineage-20`, but the two forks disagree. pulseaudio was written against AOSP's
`external/libsndfile`, which names the soname-versioned module `libsndfile12`.
The fork kept the older AOSP name `libsndfile_linux`. LineageOS 22.2 ships no
`external/libsndfile` of its own, so nothing else supplies the name.

Renaming is enough. Nothing outside `external/libsndfile/Android.bp` references
`libsndfile_linux`; the remaining `libsndfile` hits in the tree are host-side
test targets that a phone build does not build. pulseaudio reaches the headers
through `include_dirs`, not through the module, so the rename costs no headers.

## Upstream revisions that had to be substituted

Five refs in upstream's `manifests-35` do not resolve. Each is pinned to the
nearest surviving branch, recorded inline in the manifest fragments:

| upstream ref | substituted with | why |
|---|---|---|
| `android_hardware_waydroid@lineage-22.2` | `@lineage-21` | `lineage-22.2` was deleted |
| `external_stagefright-plugins@14-x86` | `@14-x86/ffmpeg-7.0` | branch renamed |
| `projectceladon/gmmlib@v22.8.0` | `intel/gmmlib@intel-gmmlib-22.10.0` | tag gone |
| `projectceladon/media-driver@v25.2.6` | `intel/media-driver@intel-media-26.1.5` | repo has no tags |
| `vendor_gapps@vic` | `android_vendor_gapps@cinnamonbun` | repo deleted |

`hardware/waydroid` gets `lineage-21` rather than `lineage-23.0` because the
latter adds a `window/1.3` HAL that Android 15 has no consumer for.

## mesa is deliberately not swapped

Upstream 22.2 adds the Waydroid mesa fork at `external/mesa` and never removes
LineageOS' `external/mesa3d`, so both end up in the module list and soong dies
with `module "mesa_src_headers" already defined` and eight more. Swapping it in
place does not work either:

```
error: hardware/google/gfxstream/guest/magma/Android.bp:22:1: "libmagma_android"
depends on undefined module "mesa_gfxstream_aemu".
```

No branch of `WayDroid-ATV/android_external_mesa3d` provides it. `lineage-18.1`
and all fourteen `lineage-18.1-mesa-*` branches were checked; none has
`src/gfxstream/aemu`. Only LineageOS' copy does. So mesa3d is left unpatched,
which also matches the rule that a LineageOS-maintained project is never
re-pointed. The Android 16 manifest swaps it because Android 16's gfxstream does
not need `mesa_gfxstream_aemu` and Android 15's does.

## Regenerating

The generated fork deltas are in `10-lineage-forks` and these are in `15-ours`,
so each keeps its own licence and regenerating one does not disturb the other.

```shell
tools/gen-fork-patches.sh <los-root> "$PWD/base-patches-35/10-lineage-forks" frameworks/base
```

`gen-fork-patches.sh` only writes the project paths it is asked for, so the
hand-written patches under `external/` and `vendor/` are untouched.

Before syncing a manifest change, run the duplicate-module preflight. It is what
catches a second copy of a project that LineageOS already ships, which is the
failure mode above:

```shell
python3 tools/check-dup-modules.py <los-root> --ours manifest/10-waydroid-projects.xml
```