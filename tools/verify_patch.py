#!/usr/bin/env python3
"""Verify a unified-diff patch against its target file.

Usage:
    python -X utf8 tools/verify_patch.py PATCH TARGET [PATCH TARGET ...]

Each (PATCH, TARGET) pair is checked independently. A patch may contain several
file sections (grouped by the ``+++ b/`` path); the section whose repo-relative
path is a suffix of TARGET is verified.

For every hunk the checker takes the "old side" (context lines `` `` plus
deletion lines ``-``) and the "new side" (context plus addition lines ``+``) and
requires one of them to appear in the target file as one contiguous block, in
order, scanned forward and never backwards across hunks:

- old side matches  -> the patch is NOT applied and its prestate is intact
  (``PASS prestate``) -- this is the check a draft patch must satisfy before
  ``git apply``;
- new side matches  -> the patch is already applied (``PASS applied``);
- mixed modes within one section -> the patch is half-applied (``FAIL``).

A match at the hunk's declared old start is labeled ``anchored``; a match
elsewhere ahead of the scan position is ``drifted``. Either counts -- line
numbers may shift when other patches touch the same file, content and order
must hold.

001/002 cannot be verified against the current oc28 tree (skipped with the
reason): 001's prestate is a nonexistent file and its poststate is fine to
check, but 002's poststate was itself rewritten by 003/004 (and draft 005), so
neither side of 002 exists on disk; verifying it would require replaying the
whole patch chain in memory.

Exit status: 0 if every required hunk matched, 1 otherwise (details on stdout).
"""

from __future__ import annotations

import sys
from pathlib import Path


def parse_patch(text: str) -> list[dict]:
    """Parse a unified diff into sections: [{path, hunks: [{old_start, old_lines, new_lines}]}]."""
    sections: list[dict] = []
    current: dict | None = None
    in_hunk = False
    for raw in text.splitlines():
        if raw.startswith("--- "):
            in_hunk = False
            current = None  # resolved via the +++ line that follows
            continue
        if raw.startswith("+++ "):
            path = raw[4:].split("\t")[0].strip()
            if path.startswith("b/"):
                path = path[2:]  # strip the git prefix; matching is by repo-relative path
            current = {"path": None if path == "/dev/null" else path, "hunks": []}
            sections.append(current)
            continue
        if raw.startswith("@@"):
            if current is None:
                raise ValueError("@@ hunk before any +++ line: %r" % raw)
            # @@ -l[,s] +l[,s] @@ ...
            old_part = raw.split()[1]
            old_start = int(old_part[1:].split(",")[0])
            current["hunks"].append({"old_start": old_start, "old_lines": [], "new_lines": []})
            in_hunk = True
            continue
        if not in_hunk or current is None or not current["hunks"]:
            continue  # diff --git / index / mode lines and inter-section junk
        hunk = current["hunks"][-1]
        if raw.startswith("\\"):
            continue  # "\ No newline at end of file"
        if raw.startswith("+"):
            hunk["new_lines"].append(raw[1:])
            continue
        if raw.startswith((" ", "-")):
            hunk["old_lines"].append(raw[1:])
            if raw.startswith(" "):
                hunk["new_lines"].append(raw[1:])
            continue
        if raw == "":
            continue
        in_hunk = False  # anything else ends the hunk
    return sections


def find_block(target: list[str], lines: list[str], start_from: int) -> int | None:
    """Index of the first contiguous occurrence of lines in target at >= start_from."""
    if not lines:
        return None
    for probe in range(max(start_from, 0), len(target) - len(lines) + 1):
        if target[probe : probe + len(lines)] == lines:
            return probe
    return None


def verify_section(patch_path: str, section: dict, target: list[str]) -> tuple[list[str], bool]:
    lines: list[str] = []
    name = section["path"] or "/dev/null"
    if name == "/dev/null":
        return ["SKIP %s: file deletion section cannot be content-verified" % patch_path], True
    if not section["hunks"]:
        return ["FAIL %s: section %s has no hunks" % (patch_path, name)], False

    cursor = 0
    modes: list[str] = []
    for i, hunk in enumerate(section["hunks"], 1):
        declared = hunk["old_start"]
        old_hit = find_block(target, hunk["old_lines"], cursor)
        new_hit = find_block(target, hunk["new_lines"], cursor)
        if old_hit is not None and (new_hit is None or old_hit <= new_hit):
            pos, mode, side = old_hit, "prestate", hunk["old_lines"]
        elif new_hit is not None:
            pos, mode, side = new_hit, "applied", hunk["new_lines"]
        else:
            modes.append("fail")
            lines.append(
                "FAIL %s [%s hunk %d]: neither old side (%d lines) nor new side (%d lines) "
                "found in order from target line %d"
                % (patch_path, name, i, len(hunk["old_lines"]), len(hunk["new_lines"]), cursor + 1)
            )
            continue
        modes.append(mode)
        kind = "anchored" if pos == declared - 1 else "drifted"
        lines.append(
            "PASS %s [%s hunk %d] %s at target line %d (%s, declared %d)"
            % (patch_path, name, i, mode, pos + 1, kind, declared)
        )
        cursor = pos + len(side)

    ok = bool(modes) and modes[0] != "fail" and all(m == modes[0] for m in modes)
    if ok and "applied" in modes:
        lines.append("NOTE %s [%s]: patch is fully applied to the target" % (patch_path, name))
    if not ok:
        lines.append("FAIL %s [%s]: hunks disagree or all failed: %s" % (patch_path, name, modes))
    return lines, ok


def verify_pair(patch_path: str, target_path: str) -> tuple[list[str], bool]:
    patch = Path(patch_path).read_text(encoding="utf-8")
    target_text = Path(target_path).read_text(encoding="utf-8")
    target = target_text.split("\n")
    if target and target[-1] == "":
        target.pop()  # trailing newline, not a content line

    sections = parse_patch(patch)
    if not sections:
        return ["FAIL %s: no file sections parsed" % patch_path], False
    norm_target = target_path.replace("\\", "/").lower()
    chosen = [s for s in sections if s["path"] and norm_target.endswith(s["path"].lower())]
    if not chosen:
        return [
            "FAIL %s: no section matches target %s (sections: %s)"
            % (patch_path, target_path, [s["path"] for s in sections])
        ], False

    lines: list[str] = []
    ok = True
    for section in chosen:
        section_lines, section_ok = verify_section(patch_path, section, target)
        lines.extend(section_lines)
        ok = ok and section_ok
    return lines, ok


def main(argv: list[str]) -> int:
    if len(argv) < 3 or len(argv) % 2 == 0:
        print(__doc__.strip())
        return 2
    ok = True
    for i in range(1, len(argv), 2):
        pair_lines, pair_ok = verify_pair(argv[i], argv[i + 1])
        for line in pair_lines:
            print(line)
        ok = ok and pair_ok
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
