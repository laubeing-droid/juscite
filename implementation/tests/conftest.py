"""Bridge-test path resolution (W2a-U16): point ``legal_anonymizer`` at the
SAME-WAVE anonymizer worktree (``legal-cn-anonymizer工作区/…/.local/worktrees/
w4-u32/src``) before any test module imports it.

Why: the machine-wide editable install (.pth) resolves ``legal_anonymizer`` to
the anonymizer main checkout, whose checked-out branch lags the wave under
test (it lacked ocr_ports_service during W2a-U14 — recorded as a pre-existing
environment failure). Each wave's bridge tests must exercise that wave's
anonymizer branch; centralizing the resolution here keeps every module
hermetic without depending on checkout order. ``JUSCITE_ANONYMIZER_SRC``
overrides; when neither resolves, modules fall back to the installed path and
their own skip guards apply (never a fake pass).

W4-U32: pin moved w2a-u18 → w4-u32 (same-wave convention; the w4-u32
anonymizer branch is a superset of the w2a-u18 chain — F42 stamp probe +
F10 at-rest parse face added additively).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_SRC = os.environ.get("JUSCITE_ANONYMIZER_SRC")
if not _SRC:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if parent.name == "jusbench工作区":
            guess = (parent.parent / "legal-cn-anonymizer工作区"
                     / "legal-cn-anonymizer" / ".local" / "worktrees"
                     / "w4-u32" / "src")
            if (guess / "legal_anonymizer" / "application"
                    / "ocr_batch_service.py").is_file():
                _SRC = str(guess)
            break
if _SRC:
    sys.path.insert(0, _SRC)
