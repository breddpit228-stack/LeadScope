from __future__ import annotations

from pathlib import Path

import app_core as _core
from app_core import *  # noqa: F401,F403

ROOT = Path(__file__).resolve().parent


def _read(name: str) -> str:
    path = ROOT / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


_extra_css = "\n".join([
    _read("workspace_loader_v56.css"),
    _read("source_quality_v57.css"),
])
_extra_js = "\n".join([
    _read("workspace_loader_v56.js"),
    _read("source_quality_v57.js"),
])

_core.HTML = _core.HTML.replace("</style>", _extra_css + "\n</style>").replace(
    "</body>", f"<script>{_extra_js}</script>\n</body>"
)
HTML = _core.HTML
app = _core.app
