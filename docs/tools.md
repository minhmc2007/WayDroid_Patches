# Tools

Five scripts. All are read-only with respect to your LineageOS tree except
`gen-fork-patches.sh`, which writes into the patch repo.

## `waydroid-patches.sh`

The entry point. See the README for usage.

```shell
waydroid-patches.sh manifest <src> [--no-aosp-swaps] [--no-sync] [-j <n>]
waydroid-patches.sh apply    <src> [--dry-run] [--no-aosp-swaps]
waydroid-patches.sh apply    <src> --layer <name> [--only <project>]
waydroid-patches.sh status   <src>
waydroid-patches.sh abort    <src>
waydroid-patches.sh revert   <src> [--yes] [--uninstall] [--purge-projects]
```

Applies with `git am -3`. Idempotence is decided by matching each patch's
author date and subject against the project history, not by
`git apply --reverse --check`: once a later patch in a series edits the same
lines, an already-applied earlier patch no longer reverse-applies cleanly and
would look like a conflict. The reverse check is kept only as a fallback for
patches that came from LineageOS itself and were merged upstream.

## `gen-fork-patches.sh`

Regenerates the derived patches in `10-lineage-forks`.

```shell
tools/gen-fork-patches.sh <los-root> <out-dir> [project-path ...]
```

For each project it fetches the WayDroid fork as a blobless partial clone and
runs:

```shell
git format-patch "$(git merge-base LOS_TIP FORK_TIP)"..FORK_TIP
```

Diffing from the **merge-base**, not the LineageOS tip, is what keeps
LineageOS commits out of the series. That is also what handles a diverged fork:
`lineage-sdk` is 7 LineageOS commits behind its fork, and diffing from the
merge-base yields the 8 Waydroid commits while those 7 stay untouched in the
checkout.

If the merge-base falls outside `GEN_FETCH_DEPTH` (default 120), it says so and
skips rather than producing a wrong series.

It only writes the project paths it is given, so `15-ours` and `20-upstream`
are never touched.

## `track-upstream.py`

Fork drift, via the GitHub compare API.

```shell
python3 tools/track-upstream.py              # table, also the body of TRACKING.md
python3 tools/track-upstream.py --json
python3 tools/track-upstream.py --regenerate # commands for stale projects
```

The head of a cross-fork compare must be `owner:branch`, not
`owner/repo:branch`. Getting that wrong 404s, which is easy to misread as "the
fork is gone".

The `action` column is the useful part:

| action | meaning |
|---|---|
| `ok` | fork is cleanly ahead, patch count matches |
| `ok (diverged, N LOS commit(s) not in fork)` | fine; `gen-fork-patches.sh` diffs from the merge-base |
| `nothing to do (fork has no commits we lack)` | e.g. `TvSettings`, 2 commits behind |
| `REGENERATE` | fork moved, regenerate that project |

## `check-dup-modules.py`

Preflight for the mistake that cost the most time here: adding a project at a
path the ROM manifest does not have, when the *same upstream project* is
already present at a *different* path. Upstream's Android 15 manifest has this
bug with mesa, which it adds at `external/mesa` while LineageOS ships
`external/mesa3d`.

```shell
python3 tools/check-dup-modules.py <src>
python3 tools/check-dup-modules.py <src> --ours manifest/10-waydroid-projects.xml
```

Soong fails with `module "X" already defined` when two projects declare the same
module name and neither uses a `soong_namespace`. Checking the manifest *names*
does not catch it, because the two projects have different manifest names
(`intel/gmmlib` vs `platform/external/gmmlib`, and likewise for mesa). This
compares the module names declared in `Android.bp` and `Android.mk` instead.

With `--ours` it only considers modules declared by your manifest fragments,
which is both much faster and the check you want after editing one. Modules in
files using `soong_namespace` are skipped, since those cannot collide.

## `xml-paths.py`

Used by `waydroid-patches.sh` to read project paths out of the manifest
fragments.

```shell
python3 tools/xml-paths.py <file>...            # print declared project paths
python3 tools/xml-paths.py --no-remove <file>... # exit 1 if any remove-project
```

Parses with `ElementTree`, not `grep`, because the fragments carry
documentation comments containing example markup such as `<project path="X"/>`
and the literal string `<remove-project>`. A grep for either picks up the
examples and produces wrong answers.