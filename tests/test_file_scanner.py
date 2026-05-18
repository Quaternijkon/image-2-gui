from pathlib import Path

import pytest

from app.core.config import InputConfig
from app.core.file_scanner import scan_input_images


def test_scan_input_images_filters_extensions_and_skips_hidden_temp_files(tmp_path, make_image):
    make_image(tmp_path / "b.JPG", image_format="JPEG")
    make_image(tmp_path / "a.png")
    make_image(tmp_path / ".hidden.png")
    make_image(tmp_path / "~$temp.png")
    make_image(tmp_path / "ignore.gif", image_format="GIF")
    nested = tmp_path / "nested"
    make_image(nested / "c.png")

    result = scan_input_images(
        InputConfig(input_dir=tmp_path, recursive=False, extensions=["PNG", ".jpg"])
    )

    assert [image.path.name for image in result.images] == ["a.png", "b.JPG"]
    assert result.images[0].width == 32
    assert result.images[0].height == 24
    assert result.images[0].format == "PNG"
    assert result.issues == []


def test_scan_input_images_recurses_and_reports_invalid_images(tmp_path, make_image):
    make_image(tmp_path / "nested" / "good.webp", image_format="WEBP")
    bad = tmp_path / "broken.png"
    bad.write_text("not an image", encoding="utf-8")

    result = scan_input_images(InputConfig(input_dir=tmp_path, recursive=True))

    assert [image.path.name for image in result.images] == ["good.webp"]
    assert len(result.issues) == 1
    assert result.issues[0].code == "invalid_image"
    assert result.issues[0].path == bad


def test_scan_input_images_allows_missing_input_dir_for_generate_mode(tmp_path):
    result = scan_input_images(InputConfig(mode="generate", input_dir=tmp_path / "missing"))

    assert result.images == []
    assert result.issues == []


def test_scan_input_images_rejects_missing_input_dir_for_edit_mode(tmp_path):
    with pytest.raises(FileNotFoundError, match="input directory does not exist"):
        scan_input_images(InputConfig(mode="edit", input_dir=tmp_path / "missing"))


def test_mask_matching_prefers_exact_then_suffix_then_dot_suffix(tmp_path, make_image):
    source = make_image(tmp_path / "product_001.png")
    mask_dir = tmp_path / "masks"
    exact = make_image(mask_dir / "product_001.png", mode="RGBA", color=(0, 0, 0, 128))
    make_image(mask_dir / "product_001_mask.png", mode="RGBA", color=(0, 0, 0, 128))

    result = scan_input_images(InputConfig(input_dir=tmp_path, mask_dir=mask_dir))

    assert result.images[0].path == source
    assert result.images[0].mask_path == exact
    assert result.issues == []


def test_mask_matching_reports_same_priority_conflict(tmp_path, make_image, monkeypatch):
    make_image(tmp_path / "product_001.png")
    mask_dir = tmp_path / "masks"
    mask = make_image(mask_dir / "product_001_mask.png", mode="RGBA", color=(0, 0, 0, 128))
    original_iterdir = Path.iterdir

    def fake_iterdir(path):
        if path == mask_dir:
            return iter([mask, mask])
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", fake_iterdir)

    result = scan_input_images(InputConfig(input_dir=tmp_path, mask_dir=mask_dir))

    assert result.images[0].validation_status == "validation_failed"
    assert result.issues[0].code == "mask_conflict"


def test_mask_validation_reports_dimension_mismatch_and_missing_alpha(tmp_path, make_image):
    make_image(tmp_path / "product_001.png", size=(32, 24))
    mask_dir = tmp_path / "masks"
    make_image(mask_dir / "product_001.png", size=(16, 16), mode="RGB")

    result = scan_input_images(InputConfig(input_dir=tmp_path, mask_dir=mask_dir))

    assert result.images[0].validation_status == "validation_failed"
    assert {issue.code for issue in result.issues} == {
        "mask_dimension_mismatch",
        "mask_missing_alpha",
    }
