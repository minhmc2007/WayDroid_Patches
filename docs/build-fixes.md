# Build fixes in `15-ours`

Ten patches, hand written, under Apache-2.0. They sit apart from the GPL-3.0 fork
deltas on purpose, so Apache-2.0 never appears to cover upstream's work.

Seven fix a defect in a project as its own upstream publishes it. The other three
are local configuration and touch no upstream code. Every fix was made after a
build failed, and every commit message quotes the error that prompted it.

| patch | change | why |
|---|---|---|
| `external/rust/hbm/0001` | `libash_latest_rust` to `libash_rust` | hbm `main` names a crate no 23.2 tree defines |
| `external/rust/hbm/0002` | disable hbm | hbm needs ash 0.38+, this tree carries 0.37.3 |
| `external/rust/android-crates-io/0001` | set `drm_syncobj_handle.point` | AOSP pairs drm-ffi 0.9.0 with a drm-sys that has the field |
| `external/minigbm/0001` | drop the hbm dependency | soong rejects a live module that depends on a disabled one |
| `external/mesa3d/0001` | call `ld.lld` by absolute path | the meson rule runs with a PATH holding no AOSP clang directory |
| `prebuilts/mesa-tools/0001` | symlink `libxml2.so.2` | bundled `libLLVM.so.20.1` wants a soname the host does not have |
| `external/tensorflow/0001` | add the `neon_2_sse` include dir | `neon_check.h` includes `NEON_2_SSE.h` on x86 |

The remaining three are configuration, not defect fixes:

| patch | change | why |
|---|---|---|
| `device/waydroid/waydroid/0001` | set `AXION_MAINTAINER` and `AXION_PROCESSOR` | AxionOS exports them as About phone properties |
| `packages/apps/FaceUnlock/0001` | drop four Megvii `required:` entries | the prebuilts carry `android_arm64` srcs only |
| `build/make/0001` | stop calling `setup_ccache` | it exports `USE_CCACHE=1` on every build |

## Why hbm is disabled rather than fixed

`hbm` is Waydroid's Vulkan and DRM host buffer manager, pulled in by our own
manifest at `refs/heads/main` the same way upstream's manifest does. Its `main`
branch targets ash 0.38 or later. `external/rust/hbm/hbm/src/sash.rs` uses the
`ash::khr` and `ash::ext` submodules along with the struct builder methods
`.push_next()`, `.src_offset()` and `.application_name()`.

LineageOS 23.2 ships ash 0.37.3, which offers `pub mod extensions` and no
builders at all. Substituting the WayDroid-ATV fork of
`external/rust/android-crates-io` changes nothing, since that fork is also
0.37.3. The result is 68 errors.

Two ways out. Disable hbm, which is what these patches do. Or add ash 0.38 or
later to the tree as a new project.

Disabling won because nothing in `device/waydroid`, `vendor/extra` or any
product file references `libhbm`, `mapper.hbm` or `hostbm`. minigbm was the only
consumer anywhere in the tree, and its reference goes in the same change.

The image has no HBM helper path as a result. Should that matter, adding ash
0.38 is the real fix and the disable should be reverted.

## The mesa-tools entry is a soname alias, not a library

`prebuilts/mesa-tools/root/lib64/libLLVM.so.20.1` links against `libxml2.so.2`,
the soname belonging to libxml2 2.9. The prebuilt carries no libxml2 in
`root/lib64`, and the `mesa_clc` wrapper places only that directory on
`LD_LIBRARY_PATH`, so the name has to resolve from the host. Arch provides
libxml2 2.15, whose soname is `libxml2.so.16`.

The patch symlinks the newer soname onto the old name, and shader compilation
was verified to produce SPIR-V. Since this is an alias rather than the library
LLVM 20 was built against, any mesa path needing a genuine ABI 2.9 symbol would
still fail. The wrapper verifies only files carrying a `.sha256` beside them,
and this symlink has none, so it is neither verified nor clobbered.

## The drm-ffi entry is an AOSP inconsistency

`external/rust/android-crates-io` is a LineageOS project this repo does not
otherwise modify. Inside AOSP's own snapshot `crates/drm-ffi` sits at version
0.9.0 while its `Cargo.toml` pins `drm-sys` 0.8.0, and the `drm-sys` actually
used declares a `point` field the 0.9.0 initializers never set:

```
error[E0063]: missing field `point` in initializer of `drm_sys::drm_syncobj_handle`
```

`drm-ffi` never reads the field, so `0` is the right value. It is a `u64` rather
than a pointer.

## The tensorflow entry needs three targets, not one

`NEON_2_SSE.h` is Intel's shim, reimplementing the ARM NEON intrinsics on top of
SSE so TFLite's optimized kernels keep their fast path on x86. `neon_check.h`
includes it whenever `__SSE4_1__` is defined and `TF_LITE_DISABLE_X86_NEON` is
not, which describes every x86_64 compile of these sources. The header itself is
present at `external/neon_2_sse`, so what is missing is an include path.

171 sources reach `optimized_ops.h`, so the include dir goes on the targets that
compile any of them: `libtflite_kernel_utils` and `libtflite_kernels`, which had
none, and `libtensorflowlite_xnnpack_jni`, which had XNNPACK's directories but
not this one.

Two things that look like they need fixing and do not. `libtflite_static`
compiles `neon_tensor_utils.cc` too, but it is defined in
`tensorflow/lite/tflite_static.bp`, and Soong parses only files named
`Android.bp`; that file is absent from the 22 entries under `external/tensorflow`
in `out/.module_paths/Android.bp.list`. And `TF_LITE_DISABLE_X86_NEON`, which
`tflite_defaults` already sets, would make the build pass at the cost of forcing
the Portable kernels.

## The FaceUnlock entry is a workaround

AxionOS hardcodes a static dependency on `vendor.aospa.biometrics.face` in
`frameworks/base/services/core`, and that library's source lives in
`packages/apps/FaceUnlock`. Thirteen files under
`services/core/java/com/android/server/biometrics/sensors/face/sense/` import it.

That hardcoding is the actual problem. `TARGET_FACE_UNLOCK_SUPPORTED` only
decides whether FaceUnlock enters `PRODUCT_PACKAGES`, and because the namespace
reaches `ALL_MODULES` regardless, kati validates the `required:` list whether or
not the app is installed. The four Megvii prebuilts declare `android_arm64`
srcs alone, so on x86_64 no variant is emitted and the required deps check fails.

Dropping the four entries is the smallest change that works. Gating the
`frameworks/base` dependency on a product variable would be the proper fix, and
would also let a target without the HAL skip the namespace entirely.

## Regenerating

The fork deltas sit in `10-lineage-forks` and these sit in `15-ours`, so each
keeps its own licence and regenerating one leaves the other alone.

```shell
tools/gen-fork-patches.sh <los-root> "$PWD/base-patches-36/10-lineage-forks" frameworks/base
```

`gen-fork-patches.sh` writes only the project paths it is given, leaving the
hand written patches under `external/` untouched.