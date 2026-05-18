from pathlib import Path

import pytest
from PIL import Image


@pytest.fixture
def make_image():
    def _make_image(
        path: Path,
        *,
        size: tuple[int, int] = (32, 24),
        mode: str = "RGB",
        color: tuple[int, ...] = (255, 0, 0),
        image_format: str | None = None,
    ) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new(mode, size, color)
        image.save(path, format=image_format)
        return path

    return _make_image
