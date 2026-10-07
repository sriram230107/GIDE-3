import shutil
from pathlib import Path
from uuid import UUID
from app.core.config import settings

SUBDIRS = ("sources", "images", "slides", "keyframes", "tmp")


def get_storage_path() -> Path:
    p = Path(settings.STORAGE_DIR)
    p.mkdir(parents=True, exist_ok=True)
    for s in SUBDIRS:
        (p / s).mkdir(parents=True, exist_ok=True)
    return p


def save_uploaded_source(source_id: UUID, filename: str, file_obj) -> str:
    storage = get_storage_path()
    ext = Path(filename).suffix.lower()
    dest_path = storage / "sources" / f"{source_id}{ext}"
    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file_obj, f)
    return str(dest_path)


def get_source_file_path(relative_or_abs: str) -> Path:
    p = Path(relative_or_abs)
    return p if p.is_absolute() else get_storage_path() / relative_or_abs


def media_url_for(source_id: UUID, file_path: str) -> str:
    return f"/storage/sources/{source_id}{Path(file_path).suffix.lower()}"
