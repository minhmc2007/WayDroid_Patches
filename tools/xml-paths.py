#!/usr/bin/env python3
"""Inspect manifest fragments for waydroid-patches.sh.

  xml-paths.py <file>...            print every declared project path
  xml-paths.py --no-remove <file>.. exit 1 if any <remove-project> is present

Used by waydroid-patches.sh so that `revert` knows which project directories our
own manifest introduced, and so the default (pure-add) manifest can be proven free
of <remove-project> entries.

Parsed with ElementTree rather than grep, because the fragments are full of
documentation comments containing example markup such as
`<project path="X" .../>` and the words "<remove-project>", which must not be
mistaken for real entries.
"""
import sys
import xml.etree.ElementTree as ET


def main(argv):
    args = list(argv[1:])
    check_no_remove = False
    if args and args[0] == "--no-remove":
        check_no_remove = True
        args = args[1:]

    bad = 0
    for path in args:
        try:
            root = ET.parse(path).getroot()
        except (ET.ParseError, OSError) as exc:
            print(f"error: cannot parse {path}: {exc}", file=sys.stderr)
            bad = 1
            continue

        # Only the default (pure-add) fragments must be free of remove-project.
        # 20-aosp-swaps.xml is opt-in and is supposed to contain them.
        if check_no_remove:
            for node in root.iter("remove-project"):
                name = node.get("name") or node.get("path")
                print(f"remove-project: {name}", file=sys.stderr)
                bad = 1

        if not check_no_remove:
            for node in root.iter("project"):
                p = node.get("path")
                if p:
                    print(p)

    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
