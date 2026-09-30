# Build fixes in `15-ours`

These live in layer `15-ours`, under Apache-2.0, deliberately kept apart from
the GPL-3.0 fork deltas. They are hand-written patches against projects that
have drifted past what LineageOS 23.2 provides, or that ship without a
LineageOS-side fix.

Each one was made only after a build failed, and each commit message quotes the
actual error.

| patch | project | why |
|---|---|---|
| `external/rust/hbm/0001` | `libash_latest_rust` → `libash_rust` | hbm's `main` wants a crate name no 23.2 tree defines |
| `external/rust/hbm/0002` | disable all six hbm modules | hbm needs ash 0.38+; this tree has 0.37.3 |
| `external/rust/android-crates-io/0001` | set `drm_syncobj_handle.point` | AOSP ships drm-ffi 0.9.0 against a drm-sys that has the field |
| `external/minigbm/0001` | drop the hbm dependency | soong refuses a live module depending on a disabled one |
| `external/mesa3d/0001` | call `ld.lld` by absolute path | the meson rule's PATH has no AOSP clang directory |
| `prebuilts/mesa-tools/0001` | symlink `libxml2.so.2` | the bundled `libLLVM.so.20.1` needs a soname the host does not have |

## Why hbm is disabled rather than fixed

`hbm` is Waydroid's Vulkan/DRM host buffer manager, added by our own manifest at
`refs/heads/main` exactly as upstream's manifest does. Its `main` branch is
written against ash 0.38+: `external/rust/hbm/hbm/src/sash.rs` uses the
`ash::khr` and `ash::ext` submodules and the struct builder methods
(`.push_next()`, `.src_offset()`, `.application_name()`).

LineageOS 23.2 provides ash 0.37.3, which has `pub mod extensions` and no
builders. Swapping `external/rust/android-crates-io` for the WayDroid-ATV fork
does **not** help, because that fork is also 0.37.3. The result is 68 errors.

Two ways out:

1. disable hbm, which is what these patches do, or
2. add ash 0.38+ to the tree as a new project.

Option 1 was chosen because nothing in `device/waydroid`, `vendor/extra` or any
product file references `libhbm`, `mapper.hbm` or `hostbm`. minigbm was the only
consumer anywhere in the tree, and its reference is removed in the same change.

**Cost:** the image has no HBM helper path. If that turns out to matter, option 2
is the real fix and option 1 should be reverted.

## The mesa-tools one is a soname alias, not a real library

`prebuilts/mesa-tools/root/lib64/libLLVM.so.20.1` is linked against
`libxml2.so.2`, the soname of libxml2 2.9. The prebuilt ships no libxml2
in `root/lib64`, and the `mesa_clc` wrapper puts only that directory on
`LD_LIBRARY_PATH`, so it has to resolve from the host. Arch has libxml2
2.15, whose soname is `libxml2.so.16`.

The patch symlinks the newer soname to the old name. Shader compilation
was verified to work. This is an alias, not the library LLVM 20 was built
against, so any mesa path needing a real ABI 2.9 symbol would still fail.
The wrapper only SHA-256 verifies files that have a `.sha256` beside them,
and this symlink has none, so it is neither verified nor clobbered.

## The drm-ffi one is an AOSP inconsistency, not ours

`external/rust/android-crates-io` is a LineageOS project this repo never
modifies. Inside AOSP's own snapshot, `crates/drm-ffi` is version 0.9.0 while its
`Cargo.toml` pins `drm-sys` 0.8.0, and the `drm-sys` actually used declares a
`point` field the 0.9.0 initializers do not set:

```
error[E0063]: missing field `point` in initializer of `drm_sys::drm_syncobj_handle`
```

`drm-ffi` never reads the field, so `0` is the correct value. It is a `u64`, not
a pointer.

## Regenerating

The generated fork deltas are in `10-lineage-forks` and these are in `15-ours`,
so each keeps its own licence and regenerating one does not disturb the other.

```shell
tools/gen-fork-patches.sh <los-root> "$PWD/base-patches-36/10-lineage-forks" frameworks/base
```

`gen-fork-patches.sh` only writes the project paths it is asked for, so the
hand-written patches under `external/` are untouched.
