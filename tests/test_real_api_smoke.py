import asyncio
import os

import pytest

from app.core.config import AppConfig
from app.core.models import OutputPlan, TaskPlan
from app.core.openai_image_client import CompletedImage, OpenAIImageClient


pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY")
    or os.environ.get("GPT_IMAGE_BATCH_RUN_REAL_API_SMOKE") != "1",
    reason="real OpenAI smoke test requires OPENAI_API_KEY and GPT_IMAGE_BATCH_RUN_REAL_API_SMOKE=1",
)


def test_real_openai_generate_smoke_guarded_by_env(tmp_path):
    task = TaskPlan(
        task_id="smoke-1",
        mode="generate",
        rendered_prompt="Create a simple one pixel style test image.",
        output_plan=OutputPlan(
            final_path=tmp_path / "final" / "smoke.png",
            partials_dir=tmp_path / "partials" / "smoke-1",
            failed_dir=tmp_path / "failed",
            thumbnails_dir=tmp_path / "thumbs",
        ),
    )
    config = AppConfig(
        prompt={"template": "Create"},
        image={"size": "auto", "quality": "auto", "output_format": "png"},
        execution={"timeout_seconds": 120},
    )

    results = asyncio.run(OpenAIImageClient(config).run_task(task))

    assert any(isinstance(result, CompletedImage) and result.b64_json for result in results)
