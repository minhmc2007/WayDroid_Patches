#!/usr/bin/env python3
"""
track-upstream.py - report how far the Waydroid-ATV forks have moved relative to
LineageOS, so it is obvious when a fork gains/loses commits and patches need
regenerating.

Two things are tracked:

1. *patched* repos (frameworks/base, frameworks/av, ...). These are kept as the
   LineageOS checkout and our generated patch series layers the fork delta on top.
   The GitHub compare API tells us ahead_by/behind_by; if behind_by is non-zero the
   fork has LineageOS commits we do not carry, and layer 10 must be regenerated.

2. *synced* repos (device/waydroid/waydroid, vendor/extra, ...). These are plain
   repo projects, so `repo sync` is always current. We only list them so the
   manifest can be audited for missing/new projects.

Usage:
  track-upstream.py                 # human readable summary
  track-upstream.py --json          # machine readable
  track-upstream.py --regenerate    # print the gen-fork-patches.sh command to run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from xml.etree import ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MANIFEST = os.path.join(ROOT, "manifest", "10-waydroid-projects.xml")
FORKS_DIR = os.path.join(ROOT, "base-patches-36", "10-lineage-forks")

API = "https://api.github.com"
UA = "waydroid-lineage-patches-tracker"

# LineageOS repo (GitHub) whose fork we patch, -> the WayDroid-ATV fork + branch.
# Key is the in-tree project path.
PATCHED = {
    "frameworks/base":       ("LineageOS/android_frameworks_base",       "WayDroid-ATV/android_frameworks_base",       "lineage-23.2"),
    "frameworks/av":         ("LineageOS/android_frameworks_av",         "WayDroid-ATV/android_frameworks_av",         "lineage-23.2"),
    "frameworks/native":     ("LineageOS/android_frameworks_native",     "WayDroid-ATV/android_frameworks_native",     "lineage-23.2"),
    "system/core":           ("LineageOS/android_system_core",           "WayDroid-ATV/android_system_core",           "lineage-23.2"),
    "system/vold":           ("LineageOS/android_system_vold",           "WayDroid-ATV/android_system_vold",           "lineage-23.2"),
    "hardware/interfaces":   ("LineageOS/android_hardware_interfaces",   "WayDroid-ATV/android_hardware_interfaces",   "lineage-23.2"),
    "lineage-sdk":           ("LineageOS/android_lineage-sdk",           "WayDroid-ATV/android_lineage-sdk",           "lineage-23.2"),
    "packages/apps/TvSettings": ("LineageOS/android_packages_apps_TvSettings", "WayDroid-ATV/android_packages_apps_TvSettings", "lineage-23.2"),
}

# Branch used to compare (LineageOS release we track).
LOS_BRANCH = "lineage-23.2"


def _get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) and attempt < 3:
                time.sleep(2 * (attempt + 1))
                continue
            return {"__error__": f"HTTP {e.code} {e.reason}"}
        except Exception as e:  # noqa: BLE001
            if attempt < 3:
                time.sleep(1 + attempt)
                continue
            return {"__error__": str(e)}
    return {"__error__": "unreachable"}


def compare(los_repo: str, fork_repo: str, branch: str) -> dict:
    # The head of a cross-fork compare is "owner:branch", not "owner/repo:branch".
    owner = fork_repo.split("/", 1)[0]
    url = f"{API}/repos/{los_repo}/compare/{LOS_BRANCH}...{owner}:{branch}"
    d = _get(url)
    if "__error__" in d:
        return {"error": d["__error__"]}
    return {
        "status": d.get("status"),
        "ahead": d.get("ahead_by"),
        "behind": d.get("behind_by"),
        "commits": d.get("total_commits"),
        "files": len(d.get("files", []) or []),
        "base": (d.get("base_commit") or {}).get("sha", "")[:9],
        "merge_base": (d.get("merge_base_commit") or {}).get("sha", "")[:9],
    }


def patch_count(project: str) -> int:
    d = os.path.join(FORKS_DIR, project)
    if not os.path.isdir(d):
        return 0
    return sum(1 for f in os.listdir(d) if f.endswith(".patch"))


def manifest_projects() -> list[tuple[str, str, str]]:
    if not os.path.exists(MANIFEST):
        return []
    root = ET.parse(MANIFEST).getroot()
    out = []
    for p in root.findall("project"):
        out.append((p.get("path"), p.get("name"), p.get("revision")))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--regenerate", action="store_true")
    args = ap.parse_args()

    rows = []
    for proj, (los, fork, branch) in sorted(PATCHED.items()):
        info = compare(los, fork, branch)
        info["project"] = proj
        info["patches"] = patch_count(proj)
        ahead = info.get("ahead") or 0
        behind = info.get("behind") or 0
        have = info["patches"]

        if have == 0 and ahead == 0:
            # The fork has nothing we do not already have, so there is nothing
            # to generate. packages/apps/TvSettings is the known case: it is
            # pure ATV and LineageOS is ahead of it.
            info["action"] = "nothing to do (fork has no commits we lack)"
        elif have == 0:
            info["action"] = "NOT GENERATED YET"
        elif have != ahead:
            info["action"] = f"REGENERATE (fork is {ahead} ahead, {have} on disk)"
        elif behind:
            # Divergence is fine: gen-fork-patches.sh diffs from the merge-base,
            # so the series holds only the Waydroid commits and LineageOS commits
            # the fork never saw stay untouched in the checkout.
            info["action"] = f"ok (diverged, {behind} LOS commit(s) not in fork)"
        else:
            info["action"] = "ok"
        rows.append(info)

    if args.json:
        json.dump({"patched": rows, "synced": manifest_projects()}, sys.stdout, indent=2)
        print()
        return 0

    if not sys.stdout.isatty():
        pass

    print(f"Waydroid-ATV fork tracking vs LineageOS {LOS_BRANCH}")
    print("=" * 100)
    hdr = f"{'project':<30}{'status':<10}{'ahead':>6}{'behind':>7}{'files':>7}{'patches':>9}   action"
    print(hdr)
    print("-" * 100)
    for r in rows:
        if "error" in r:
            print(f"{r['project']:<30}{'ERROR':<10} {r['error']}")
            continue
        print(f"{r['project']:<30}{str(r['status']):<10}{r['ahead']:>6}{r['behind']:>7}"
              f"{r['files']:>7}{r['patches']:>9}   {r['action']}")

    stale = [r for r in rows if r.get("action", "").startswith(("REGENERATE", "NOT"))]
    if stale and not args.regenerate:
        print()
        print("Run with --regenerate to see the commands that rebuild stale patch layers.")
    if args.regenerate:
        print()
        print("# rebuild the stale layers:")
        for r in stale:
            print(f"GEN_WORKDIR=$PWD/_scratch bash tools/gen-fork-patches.sh "
                  f"<LineageOS-root> base-patches-36/10-lineage-forks {r['project']}")

    print()
    print(f"Synced (never patched, plain repo projects): {len(manifest_projects())} entries in "
          f"manifest/10-waydroid-projects.xml")
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
