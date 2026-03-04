from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse


router = APIRouter(include_in_schema=False)

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_INDEX_FILE = _STATIC_DIR / "index.html"


@router.get("/")
def app_shell(request: Request):
    root_path = request.scope.get("root_path", "").rstrip("/")
    html = _INDEX_FILE.read_text(encoding="utf-8").replace("__ROOT_PATH__", root_path)
    return HTMLResponse(html)
