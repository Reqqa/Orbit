"""Receipt images on disk.

The database stores a reference, never the bytes (docs/SPEC.md section 5.1 step 2).
Files are named by their own SHA-256, which makes storage idempotent and gives the
extraction cache its key for free. A real deployment would put these in private
object storage with signed URLs and a 90-day retention job (section 10).
"""

import hashlib
from pathlib import Path

from app.config import BACKEND_DIR

MEDIA_DIR = BACKEND_DIR / "media"


def save_media(image_bytes: bytes, suffix: str = ".png") -> str:
    """Store the image and return the reference to put on the message row."""
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(image_bytes).hexdigest()
    path = MEDIA_DIR / f"{digest}{suffix}"
    if not path.exists():
        path.write_bytes(image_bytes)
    return path.name


def load_media(media_ref: str | None) -> bytes | None:
    """Read an image back, or None when there is nothing stored."""
    if not media_ref:
        return None
    # Defend against a reference trying to escape the media directory.
    path = (MEDIA_DIR / Path(media_ref).name).resolve()
    if not path.is_file() or MEDIA_DIR.resolve() not in path.parents:
        return None
    return path.read_bytes()
