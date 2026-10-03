# Build fixes in `15-ours`

Fifteen patches, hand written, under Apache-2.0. They sit apart from the GPL-3.0
fork deltas on purpose, so Apache-2.0 never appears to cover upstream's work.

Twelve fix a defect in a project as its own upstream publishes it. The other three
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
| `hardware/interfaces/0001` | annotate `loadHardcodedEffects` | the constructor calls it without `mMutex` held |
| `hardware/interfaces/0002` | implement `setNodeCeiling`, `clearNodeCeiling` | IPower V6 made both pure virtual |
| `external/zlib-ng/0001` | drop AVX512 and AVX2 from the x86 build | apexd SIGILL in `deflateCopy`, then SIGSEGV in `chunkmemset_avx2` |
| `external/zlib-ng/0002` | define `HAVE_ATTRIBUTE_ALIGNED` | 32-bit zygote SIGSEGV in `chunkmemset_safe_ssse3` and `inflate_fast_ssse3`; fixed and confirmed |

The remaining three are configuration, not defect fixes:

| patch | change | why |
|---|---|---|
| `device/waydroid/waydroid/0001` | set `AXION_MAINTAINER` and `AXION_PROCESSOR` | AxionOS exports them as About phone properties |
| `packages/apps/FaceUnlock/0001` | drop four Megvii `required:` entries | the prebuilts carry `android_arm64` srcs only |
| `build/make/0001` | stop calling `setup_ccache`, honour falsy `USE_CCACHE` | it exports `USE_CCACHE=1` on every build; `USE_CCACHE=0` enabled ccache |
| `build/make/0002` | drop the hard 6-job clamp in `envsetup.sh` | it overrode `perfConfigForRam` on any host with more than six cores |

## Why the job cap had to go

`perfConfigForRam` in `envsetup.sh` already derives a job count from RAM and
returns `cpu_count` for anything under 32 GiB, and `setupPerf` returns early at
32 GiB and above without setting anything at all. A separate clamp then forced
the result down to 6:

```bash
if (( jobs > 6 )); then
  jobs=6
fi
```

So the RAM scaling decided 12 and the clamp overruled it. Verified against this
host, where `hostRamGb` rounds 15.3 GiB up to 16 and therefore takes the
`ram < 32` branch:

| | value |
| --- | --- |
| `perfConfigForRam` | `jobs=12  GOMEMLIMIT=16GiB  java=8g` |
| with the clamp | `NINJA_ARGS=-j6` |
| without the clamp | `NINJA_ARGS=-j12` |

The `cpu_count` clamp stays as a sanity bound, and so does `highmem_jobs`, which
stays at 1 under 16 GiB. That one is not a job cap in the ordinary sense: it is
`NINJA_HIGHMEM_NUM_JOBS`, the limit on concurrent high-memory edges such as LTO
and dex2oat, and it is what actually keeps a low-RAM host out of swap. Raising
the ordinary job count to 12 while leaving that at 1 gets the parallelism
without giving up the protection.

Note this is AxionOS's own heuristic, added in `54170ff` on the
`AxionAOSP/android_build` remote, not something LineageOS maintains.

## Why the ccache entry touches two files

`setup_ccache` in `envsetup.sh` exports `USE_CCACHE=1` and points `CCACHE_EXEC`
at ccache on every build, and leaves `CCACHE_MAXSIZE` unbounded. Commenting out
the call fixes that, but on its own it is not enough, because the gate in
`core/ccache.mk` only matched one spelling of off:

```make
ifneq ($(filter-out false,$(USE_CCACHE)),)
```

`filter-out` returns its whole argument list minus the words it is given, so
every other value survived, `0` and `no` and `off` included. `USE_CCACHE=0`
enabled ccache. This matters because the two gates disagree: soong's
`IsEnvTrue` rejects `0`, but `ccache.mk` is what sets `CC_WRAPPER` and the
`CCACHE_*` variables soong then consumes, and it is the permissive one.

The symptom did not look like a ccache problem at all:

```
ccache: error: Not a directory
```

Nothing created `~/.cache/ccache` once `setup_ccache` was disabled, and soong
passes `-B ~/.cache/ccache` to nsjail. nsjail's `-B` creates a missing bind
source as an empty regular file, so ccache was handed a file where it wanted a
directory and every compile failed at the wrapper. The directory was recreated
by hand to get the build moving; the patch makes the configuration correct
instead of the symptom.

Nothing is removed. Verified with real `make` against both expressions:

| `USE_CCACHE` | before | after |
| --- | --- | --- |
| empty | off | off |
| `0` | **on** | off |
| `1` | on | on |
| `false` | off | off |
| `no`, `off` | **on** | off |
| `yes`, `true`, `2` | on | on |

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

## The zlib-ng entry needs a flag change and a source change

AxionOS swaps AOSP zlib out for zlib-ng (`axion.xml:56` removes
`external/zlib`, `axion.xml:199` adds `external/zlib-ng`). `libz_defaults` is a
`cc_defaults` on `libz`, so the five `-mavx512*` flags it carried applied to every
source in the module, not only the dispatched kernels. At `-O3` clang
autovectorised ordinary code such as `deflate.c`, which is where the EVEX
`vmovups %zmm0` came from, and apexd died with `ILL_ILLOPN` mounting APEX. The
`functable.c` dispatch was never at fault and still gates every wide kernel on
`has_avx512_common`.

The flags, the `X86_AVX512` and `X86_AVX512VNNI` defines and the four `arch/x86`
sources come out of `Android.bp`. The vpclmulqdq CRC kernel cannot follow that
route, because its source guard is `X86_VPCLMULQDQ_CRC`, which is also what
gates its declarations in `x86_functions.h` and its dispatch in `functable.c`.
Dropping the define would work but edits `Android.bp` again, so the guard gains
`&& defined(X86_AVX512)` instead and `Android.bp` stays untouched.
`crc32_fold_vpclmulqdq_tpl.h` is built entirely from `_mm512_*` intrinsics and
cannot compile without `avx512f`, so `X86_VPCLMULQDQ_CRC` alone is a combination
that was never buildable. `functable.c` already required `has_avx512_common`
before selecting the kernel, so nothing is lost. `crc32_pclmulqdq.c` is
unaffected: `crc32_fold_pclmulqdq_tpl.h` only reaches the zmm template when
`X86_VPCLMULQDQ` is set, and only `crc32_vpclmulqdq.c` sets it.

With AVX512 gone, apexd got further and then faulted a second time, SIGSEGV
after a 210 s stall:

```
#0 chunkmemset_avx2(unsigned char*, unsigned char*, unsigned int) +0x24a
#1 inflate +0xe84
2303a: c5 fd 6f 04 07  vmovdqa (%rdi,%rax,1),%ymm0
```

`vmovdqa` is an aligned 256-bit load, so a 32-byte-misaligned address raises
`#GP`. `functable.c` dispatches the AVX2 kernels on the AVX2 gate alone rather
than behind `has_avx512_common`, so that kernel was already selected before the
first fix and apexd had simply died earlier.

`-mvpclmulqdq` was the quiet cause of the 256-bit codegen. It implies
`__AVX__` in clang, so leaving it in permitted VEX.256 across every translation
unit, including the generic C. Since the vpclmulqdq CRC kernel is already
compiled out, the flag was dead config whose only effect was to allow the
faulting loads, so it and `X86_VPCLMULQDQ_CRC` go as well.

`slide_hash_avx2.c` carries no preprocessor guard at all, so unlike the other
three it had to leave `srcs` rather than rely on `X86_AVX2` compiling it out.

Kept: SSE2 through SSE4.2, PCLMULQDQ, BMI2 and XSAVE. PCLMULQDQ and BMI2 do not
imply AVX in clang, so the 128-bit path stays clear of 256-bit codegen and works
on any x86_64 CPU.

Verified by compiling all 41 x86_64 libz sources with the module's exact flags
under `-Werror`, then disassembling every object: 0 `ymm`, 0 `zmm`, 0 mask
registers and 0 `vmovdqa` across the whole module.

## The second zlib-ng entry is a missing define, not a missing flag

`zbuild.h` guards two macros on feature defines that no build system in this tree
ever sets:

```c
#if defined(HAVE_ATTRIBUTE_ALIGNED)
#  define ALIGNED_(x) __attribute__ ((aligned(x)))
#else
#  define ALIGNED_(x)
#endif

#ifdef HAVE_BUILTIN_ASSUME_ALIGNED
#  define HINT_ALIGNED(p,n) __builtin_assume_aligned((void *)(p),(n))
#else
#  define HINT_ALIGNED(p,n) (p)
#endif
```

`HAVE_ATTRIBUTE_ALIGNED` and `HAVE_BUILTIN_ASSUME_ALIGNED` are defined in exactly
two places, `configure:1091` and `CMakeLists.txt:587`. AxionOS builds zlib-ng
through `Android.bp`, so neither was ever set and both macros expanded to nothing.
`ALIGNED_(x)` then drops the alignment from every object in the tree while the SIMD
code keeps doing aligned accesses on it, which is the worse half of the pairing:
the access is the one that assumes, the attribute is the one that got thrown away.

Measured against the tree's own headers:

| | before | after | asked for |
|---|---|---|---|
| `_Alignof(inflate_state)` | 8 | 64 | 64 (`inflate.h:99`) |
| `_Alignof(permute_table)` | 1 | 32 | 32 (`arch/generic/chunk_permute_table.h:11`) |

`_Alignof` reports 1 because `ALIGNED_(32)` was literally absent. In the shipped
32-bit `libz.so` before the patch the table landed at `0x4fc4`, 4-byte aligned,
and `pshufb_shf_table` at `0x5318`, 8-byte aligned against the 16 that
`arch/x86/crc32_pclmulqdq_tpl.h` asks for. Both are read with `_mm_load_si128`,
which is an aligned access by definition regardless of what the attribute said, so
this was undefined behaviour in every arch and every variant, not only on x86.

After the patch, from the unstripped intermediates of the build that fixed it:

| | 32-bit `libz.so` | 64-bit `libz.so` |
|---|---|---|
| `permute_table` | `0x4fe0` | `0x60a0` |
| `pshufb_shf_table` | `0x5340` | — |

All three are 0 mod 32, so the attribute is being honoured now.

The symptom was the 32-bit zygote, respawning about every twelve seconds and never
reaching `ZygoteInit.preload` past `Class.forName`, while the 64-bit zygote came up
normally. It died in inflate reading `core-icu4j.jar` from the `com.android.i18n`
apex, at two separate offsets, both of them the `pshufb` in `GET_CHUNK_MAG` that
folds the `_mm_load_si128` of `permute_table`:

```
#00 pc 00023299  /system/lib/libz.so (chunkmemset_safe_ssse3+393)
#01 pc 000165bd  /system/lib/libz.so (inflate+8717)
```

A second coredump from the same boot, `dex2oat32` on `EasterEgg.apk`, is the other
one of the pair: `libz.so+0x23ed8`, `inflate_fast_ssse3+0x9a8`. Both crashes report
`si_code SI_KERNEL` with `err 00000000`, so `#GP` and not a page fault, which is
what a misaligned `movaps`/`movdqa` raises on 32-bit x86 and what a bad address
would not.

Neither `pshufb` faults on a bad address, which is the part worth being careful
about. In the `chunkmemset_safe_ssse3` tombstone `edi` was `base+0x28138`, the
pc-thunk constant, so `permute_table` resolved to `base+0x4fc4` and the `pshufb`
operand to `base+0x5084`, inside the module's own `.rodata`, mapped and readable.
`ecx=192` and `edx=5` are `perm_idx_lut[8]`, a valid dist-11 entry, and `eax=16`
is `sizeof(chunk_t)`. The instruction had nothing to fault on, and that is the
part the rebuild settled rather than the tombstone.

`dex2oat64` and the 64-bit zygote were unaffected, and the 64-bit `permute_table`
was under-aligned in exactly the same way before the patch, at `0x6090`. So the
alignment gap was present in the 64-bit module too; 64-bit never took the faulting
path, because x86-64 tolerates the unaligned form where 32-bit does not.

## The zygote fix is confirmed on the ROM, not inferred

Worth stating plainly, because it was not the prediction. The rebuilt `libz.so`
still contains the identical `pshufb`, at all six sites, only with the table
aligned:

```
232b9: pshufb -0x23178(%edi,%ecx), %xmm0     # was -0x23174, table 4 mod 32
23ef8: pshufb -0x23178(%ebx,%eax), %xmm0
```

Same instruction, same operands, same address arithmetic, and it no longer
faults, so the cause was the alignment of `permute_table` and not the instruction.

After rebuilding, `system/lib/libz.so` is `e22fa10e`, was `ae5f6bda`, and the
32-bit zygote completed `preload`. `coredumpctl list` shows 43 `app_process32`
entries, all of them from the boot before the rebuild, the newest at 15:32:43, and
none since a boot at 21:12. `dex2oat32` did not recur either. Still 0 `ymm` and
0 `zmm` in the rebuilt 32-bit module.

## Regenerating

The fork deltas sit in `10-lineage-forks` and these sit in `15-ours`, so each
keeps its own licence and regenerating one leaves the other alone.

```shell
tools/gen-fork-patches.sh <los-root> "$PWD/base-patches-36/10-lineage-forks" frameworks/base
```

`gen-fork-patches.sh` writes only the project paths it is given, leaving the
hand written patches under `external/` untouched.