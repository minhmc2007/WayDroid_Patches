# AGENTS.md

## Repo

Waydroid and Waydroid-ATV changes as `.patch` files, layered on a stock AxionOS checkout. Meant to apply on almost any LineageOS-based ROM. No forks. Nothing LineageOS or AxionOS maintains gets removed or re-pointed.

ROM is AxionOS 2.8, which is LineageOS 23.2 on Android 16 with AxionOS's own forks. Base branch `lineage-23.2`. Phone build, not Android TV.

Build with `. build/envsetup.sh`, then `axion <device> va` and `mka systemimage vendorimage`. `axion` replaces `lunch`.

Read `README.md`, `docs/tools.md`, `docs/build-fixes.md` before touching anything.

## Layout

| Path | What | Licence |
| --- | --- | --- |
| `base-patches-36/10-lineage-forks` | Waydroid-only commits, generated | GPL-3.0 |
| `base-patches-36/15-ours` | hand-written build fixes | Apache-2.0 |
| `base-patches-36/20-upstream` | upstream patches, verbatim | GPL-3.0 |
| `manifest/` | repo manifest fragments | |
| `tools/`, `waydroid-patches.sh` | tooling | Apache-2.0 |

Rules:

- Layer order is 10, 15, 20. Keep it.
- Never edit files in `10-` or `20-` by hand. Regenerate.
- Hand-written fixes go in `15-ours` only. Never mix licences in one layer.
- `remove-project` only for the existing AOSP swaps. Anything else: ask.
- Use existing tools in `tools/` before writing new ones.

## Talking to user

Short. Caveman style: drop filler, keep technical words exact. No greeting, no praise, no restating the task, no closing summary, no "let me know if".

Applies to every message, subagent reports included.

Drop to normal English only for: security warnings, irreversible actions (`revert --yes`, `--purge-projects`, force push, deleting files), anything where a fragment could be misread. Then back to short.

## Code rules

- No AI slop.
- Comment only when the why is not obvious from the code. One short line. Never a paragraph. Never narrate what the code does.
- No docstring essays, banner comments, or changelog comments.
- Do not overengineer. Smallest change that works. No new abstraction, flag, or config without a stated need.
- Match existing style in the file.

## Conflicts and ambiguity

If a conflict has more than one valid fix, do not pick. Stop and ask.

Format:

```
conflict: <what, file:line>
A: <fix> -- <why>
B: <fix> -- <why>
not A because: <reason>
not B because: <reason>
```

Same for missing info: ask, do not guess. Branch names, remotes, which upstream, which patches to keep.

## Collecting patches from scratch

1. Ask user for target branches: LineageOS branch and Waydroid / Waydroid-ATV branch. Do not assume `lineage-23.2`.
2. List the projects Waydroid changes. Source: the Waydroid-ATV manifest for that branch.
3. Dispatch one read-only subagent per project, in parallel (cavecrew-investigator style: caveman output, one result block per project).
4. Each subagent compares upstream to fork with the GitHub compare API, three-dot so only fork commits show:

   ```
   GET /repos/LineageOS/<repo>/compare/<los-branch>...<fork-owner>:<fork-branch>
   Accept: application/vnd.github.patch
   ```

   Ask for the patch media type. Do not rebuild patches from the JSON diff.
5. Subagent returns: project, commit count, files touched, patch path. Nothing else.
6. Compare API truncates at 250 commits. If hit, paginate or report it. Do not silently ship a partial patch.
7. Diverged fork is fine. Fork behind upstream with nothing new: skip, note in `TRACKING.md`.
8. Save to `10-lineage-forks`. Check with `tools/check-dup-modules.py` and `--dry-run` apply before reporting done.

Subagent split (cavecrew):

- investigator: compare, locate, list. Read-only.
- builder: edit of 1-2 files with known paths. Not for multi-file refactors.
- reviewer: reads the diff, returns findings only. Run on every patch set before commit.

## Commits

caveman-commit style. Conventional Commits. Subject 50 chars or less, imperative, no period. Body only when the why is not obvious. No emoji, no "this commit".

```
fix(mesa): add libxml2 soname alias
```

## Do not

- Do not run `revert --yes` or `--purge-projects` without asking.
- Do not `repo sync` over local work without asking.
- Do not add dependencies or tools the task does not need.
