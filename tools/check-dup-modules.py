#!/usr/bin/env python3
"""Detect duplicate Soong module names in a repo checkout.

`soong bootstrap` fails with "module X already defined" when two projects in the
tree declare the same module name and neither uses a `soong_namespace`. This is
easy to create with a local manifest: a project can be absent from the ROM
manifest at one path while the *same upstream project* is already present under a
different path, which is exactly what happened with gmmlib here
(`intel/gmmlib` at vendor/intel/gmmlib vs `platform/external/gmmlib` at
external/gmmlib).

Usage:
    check-dup-modules.py <source-dir> [--ours manifest.xml ...]

With --ours, only the modules declared by those manifest fragments are checked,
which is much faster and is what you want after editing a local manifest.
Exits 1 if any duplicate is found.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET

SKIP_DIRS = {".git", "out", ".repo", "prebuilts"}
BP_NAME = re.compile(r'^\s*name:\s*"([^"]+)"', re.M)
MK_NAME = re.compile(r"^\s*LOCAL_MODULE\s*:?=\s*(\S+)", re.M)
NAMESPACE = re.compile(r"soong_namespace\s*\{", re.M)


def names_in(path: str) -> set[str]:
    out: set[str] = set()
    try:
        text = open(path, errors="ignore").read()
    except OSError:
        return out
    if path.endswith("Android.bp"):
        if NAMESPACE.search(text):
            return out
        out |= set(BP_NAME.findall(text))
    elif path.endswith("Android.mk"):
        out |= set(MK_NAME.findall(text))
    return {n for n in out if len(n) > 3}


def walk_modules(root: str, only: set[str] | None = None):
    """Yield (module, [files]) for module names seen in more than one project."""
    seen: dict[str, set[str]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name not in ("Android.bp", "Android.mk"):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            for mod in names_in(full):
                if only is not None and mod not in only:
                    continue
                seen.setdefault(mod, set()).add(rel)
    return {m: sorted(f) for m, f in seen.items() if len(f) > 1}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--ours", nargs="*", metavar="XML",
                    help="only check modules declared by these manifest fragments")
    args = ap.parse_args()

    root = os.path.abspath(args.source)
    if not os.path.isdir(root):
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2

    only = None
    ours_projects: set[str] = set()
    if args.ours:
        only = set()
        for frag in args.ours:
            for node in ET.parse(frag).getroot().iter("project"):
                path = node.get("path")
                if not path:
                    continue
                ours_projects.add(path)
                base = os.path.join(root, path)
                for dirpath, _, files in os.walk(base):
                    for name in files:
                        if name in ("Android.bp", "Android.mk"):
                            only |= names_in(os.path.join(dirpath, name))
        if not only:
            print("no modules declared by the given fragments")
            return 0

    dupes = walk_modules(root, only)

    if args.ours and ours_projects:
        # Only report when the two declarations come from different projects,
        # which is the case that actually breaks soong.
        real = {}
        for mod, files in dupes.items():
            owners = {f.split("/")[0] for f in files}
            if len(owners) > 1:
                real[mod] = files
        dupes = real

    if not dupes:
        print("no duplicate module names found")
        return 0

    print(f"{len(dupes)} duplicated module name(s):")
    for mod, files in sorted(dupes.items()):
        print(f"  {mod}")
        for f in files[:4]:
            print(f"      {f}")
    print()
    print("soong bootstrap will fail with 'module already defined'.")
    print("Fix by dropping one of the two projects, or by giving it a soong_namespace.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
