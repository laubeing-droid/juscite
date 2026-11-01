"""Generate and check the delivery diff against the saved fixed-commit source only."""
from pathlib import Path
import difflib
import hashlib
import json
import subprocess

base = Path(__file__).resolve().parent
evidence = base.parent.parent / "02-opencode-v2-source"
route = "packages/app/src/shell/routes/routes.tsx"
new_path = "packages/app/src/legal-workbench/legal-workbench.tsx"
original = (evidence / route.replace("/", "__")).read_text(encoding="utf-8-sig").rstrip() + "\n"
source = (base / new_path).read_text(encoding="utf-8-sig").rstrip() + "\n"
anchor = 'import { ExtensionAttachment } from "@/runtime/extension/root"\n'
mount = "<Shell>{props.children}</Shell>"
assert original.count(anchor) == original.count(mount) == 1
modified = original.replace(anchor, anchor + 'import { LegalWorkbench } from "@/legal-workbench/legal-workbench"\n')
modified = modified.replace(mount, "<Shell>\n              <LegalWorkbench>{props.children}</LegalWorkbench>\n            </Shell>")
diff = "".join(difflib.unified_diff(original.splitlines(True), modified.splitlines(True), "a/" + route, "b/" + route))
diff += "".join(difflib.unified_diff([], source.splitlines(True), "/dev/null", "b/" + new_path))
patch = base / "opencode-v2.0.28-legal-workbench.patch"
patch.write_text(diff, encoding="utf-8", newline="\n")
folder = base / "source-check"
target = folder / route
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(original, encoding="utf-8", newline="\n")
result = subprocess.run(["git", "apply", "--check", str(patch)], cwd=folder, capture_output=True, text=True)
assert result.returncode == 0, result.stderr
checks = {
    "subject_commit": "026b106bc5d41b679ffc413264229c340871e4d3",
    "source_path": route,
    "source_sha256_normalized": hashlib.sha256(original.encode()).hexdigest(),
    "mount_count": 1,
    "new_dependency_count": 0,
    "saved_fixed_source_git_apply_check": "PASS",
    "full_checkout_git_apply_check": "NOT_RUN",
    "typecheck": "NOT_RUN",
    "build": "NOT_RUN",
    "runtime_ui": "NOT_RUN",
    "production_modified": False,
}
(base / "static-check.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(checks, ensure_ascii=False))
