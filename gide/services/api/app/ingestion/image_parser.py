from pathlib import Path
from typing import Any
from uuid import UUID


def extract_image(file_path: str, source_id: UUID, storage: Path) -> list[dict[str, Any]]:
    """A standalone image becomes one 'image' unit; text comes from the vision pass."""
    import shutil
    ext = Path(file_path).suffix.lower()
    rel = f"images/{source_id}/upload{ext}"
    (storage / "images" / str(source_id)).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(file_path, storage / rel)
    return [{"source_id": source_id, "source_type": "image", "unit_type": "image",
             "content": "[Uploaded image: awaiting vision/OCR]", "image_path": rel, "sequence_index": 0,
             "unit_metadata": {"needs_ocr": True}}]
