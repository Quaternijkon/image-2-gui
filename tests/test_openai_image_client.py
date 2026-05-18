import asyncio
from pathlib import Path

from app.core.config import AppConfig
from app.core.models import OutputPlan, TaskPlan
from app.core.openai_image_client import CompletedImage, OpenAIImageClient, PartialImage


PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="


class _Response:
    def __init__(self):
        self.data = [type("ImageData", (), {"b64_json": PNG_B64})()]
        self.usage = {"total_tokens": 12}


class _StreamingResponse:
    def __aiter__(self):
        async def _events():
            yield {
                "type": "image_generation.partial_image",
                "partial_image_index": 0,
                "b64_json": PNG_B64,
            }
            yield {
                "type": "image_generation.completed",
                "b64_json": PNG_B64,
                "usage": {"total_tokens": 5},
            }

        return _events()


class _Images:
    def __init__(self):
        self.calls = []

    async def generate(self, **kwargs):
        self.calls.append(("generate", kwargs))
        if kwargs.get("stream"):
            return _StreamingResponse()
        return _Response()

    async def edit(self, **kwargs):
        self.calls.append(("edit", kwargs))
        return _Response()


class _SdkClient:
    def __init__(self):
        self.images = _Images()


def _task(tmp_path: Path, *, mode="generate", image_path=None, mask_path=None):
    return TaskPlan(
        task_id="task-1",
        mode=mode,
        source_paths=[image_path] if image_path else [],
        mask_path=mask_path,
        rendered_prompt="prompt",
        output_plan=OutputPlan(
            final_path=tmp_path / "final" / "out.png",
            partials_dir=tmp_path / "partials" / "task-1",
            failed_dir=tmp_path / "failed",
            thumbnails_dir=tmp_path / "thumbs",
        ),
    )


def test_openai_image_client_generates_non_stream_result_without_input_fidelity(tmp_path):
    sdk = _SdkClient()
    config = AppConfig(
        prompt={"template": "prompt"},
        image={"output_format": "png"},
        execution={"timeout_seconds": 123},
    )

    result = asyncio.run(OpenAIImageClient(config, sdk_client=sdk).run_task(_task(tmp_path)))

    assert result == [CompletedImage(b64_json=PNG_B64, usage={"total_tokens": 12})]
    _, params = sdk.images.calls[0]
    assert params["model"] == "gpt-image-2"
    assert params["prompt"] == "prompt"
    assert params["output_format"] == "png"
    assert params["timeout"] == 123
    assert "input_fidelity" not in params
    assert "output_compression" not in params


def test_openai_image_client_edits_with_image_and_mask_files_then_closes_them(tmp_path):
    image = tmp_path / "input.png"
    mask = tmp_path / "mask.png"
    image.write_bytes(b"image")
    mask.write_bytes(b"mask")
    sdk = _SdkClient()
    config = AppConfig(prompt={"template": "prompt"})

    asyncio.run(
        OpenAIImageClient(config, sdk_client=sdk).run_task(
            _task(tmp_path, mode="edit", image_path=image, mask_path=mask)
        )
    )

    _, params = sdk.images.calls[0]
    assert params["image"][0].closed
    assert params["mask"].closed
    assert params["timeout"] == 240
    assert "input_fidelity" not in params


def test_openai_image_client_streams_partial_and_completed_events(tmp_path):
    sdk = _SdkClient()
    config = AppConfig(
        prompt={"template": "prompt"},
        image={"stream": True, "partial_images": 1, "save_partials": True},
    )

    result = asyncio.run(OpenAIImageClient(config, sdk_client=sdk).run_task(_task(tmp_path)))

    assert result == [
        PartialImage(index=0, b64_json=PNG_B64),
        CompletedImage(b64_json=PNG_B64, usage={"total_tokens": 5}),
    ]
    _, params = sdk.images.calls[0]
    assert params["stream"] is True
    assert params["partial_images"] == 1
