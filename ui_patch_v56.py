from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAIRS = [
    (ROOT / "static" / "workspace_v55.css", ROOT / "workspace_loader_v56.css", "/* Workspace SaaS research loader */"),
    (ROOT / "static" / "workspace_v55.js", ROOT / "workspace_loader_v56.js", "function installWorkspaceResearchLoader()"),
]
for target, fragment, marker in PAIRS:
    if not target.exists() or not fragment.exists():
        continue
    current = target.read_text(encoding="utf-8")
    if marker in current:
        continue
    extra = fragment.read_text(encoding="utf-8")
    target.write_text(current.rstrip() + "\n\n" + extra.rstrip() + "\n", encoding="utf-8")
