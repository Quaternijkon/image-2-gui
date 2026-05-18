import json

import pytest
from pydantic import ValidationError

from app.core.config import AppConfig


def test_default_config_matches_task_defaults():
    config = AppConfig(prompt={"template": "Create a clean product image"})

    assert config.api.model == "gpt-image-2"
    assert config.api.api_type == "image"
    assert config.image.size == "1024x1024"
    assert config.image.quality == "medium"
    assert config.image.output_format == "png"
    assert config.image.background == "auto"
    assert config.image.moderation == "auto"
    assert config.image.n == 1
    assert config.image.stream is False
    assert config.image.partial_images == 0
    assert config.image.save_partials is False
    assert config.execution.concurrency == 2
    assert config.execution.max_retries == 2
    assert config.execution.timeout_seconds == 240
    assert config.execution.failure_policy == "continue"
    assert config.execution.overwrite_policy == "skip_existing"


@pytest.mark.parametrize(
    ("size", "message"),
    [
        ("1024", "WxH"),
        ("1025x1024", "multiple of 16"),
        ("4096x1024", "3840"),
        ("3840x1024", "3:1"),
        ("512x512", "total pixels"),
        ("3840x3840", "total pixels"),
    ],
)
def test_invalid_size_constraints_are_rejected(size, message):
    with pytest.raises(ValidationError, match=message):
        AppConfig(prompt={"template": "Generate"}, image={"size": size})


def test_auto_size_is_accepted():
    config = AppConfig(prompt={"template": "Generate"}, image={"size": "auto"})

    assert config.image.size == "auto"


def test_transparent_background_is_rejected_for_gpt_image_2():
    with pytest.raises(ValidationError, match="transparent"):
        AppConfig(prompt={"template": "Generate"}, image={"background": "transparent"})


def test_png_output_rejects_compression():
    with pytest.raises(ValidationError, match="output_compression"):
        AppConfig(
            prompt={"template": "Generate"},
            image={"output_format": "png", "output_compression": 80},
        )


@pytest.mark.parametrize("compression", [-1, 101])
def test_compression_must_be_between_zero_and_one_hundred(compression):
    with pytest.raises(ValidationError, match="0-100"):
        AppConfig(
            prompt={"template": "Generate"},
            image={"output_format": "webp", "output_compression": compression},
        )


@pytest.mark.parametrize("partial_images", [-1, 4])
def test_partial_images_must_be_zero_to_three(partial_images):
    with pytest.raises(ValidationError, match="partial_images"):
        AppConfig(prompt={"template": "Generate"}, image={"partial_images": partial_images})


def test_empty_prompt_is_rejected_for_executable_configs():
    with pytest.raises(ValidationError, match="prompt"):
        AppConfig(prompt={"template": "   "})


def test_json_round_trip_preserves_fields():
    config = AppConfig(
        input={"input_dir": "D:/Input Images"},
        prompt={"template": "Create a studio product image"},
        image={
            "size": "1536x1024",
            "output_format": "webp",
            "output_compression": 72,
            "partial_images": 2,
        },
        output={"output_dir": "D:/Output Images"},
    )

    payload = config.model_dump_json()
    restored = AppConfig.model_validate_json(payload)

    assert restored == config
    assert json.loads(payload)["image"]["output_compression"] == 72
