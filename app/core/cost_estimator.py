from math import ceil
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.core.config import AppConfig
from app.core.models import PlannedJob


# Heuristic token-unit weights. These are not API pricing and are deliberately
# isolated here so estimates stay visibly separate from capability validation.
_SIZE_IMAGE_TOKEN_UNITS = {
    "auto": 1_000,
    "1024x1024": 1_000,
    "1024x1536": 1_500,
    "1536x1024": 1_500,
}
_DEFAULT_IMAGE_TOKEN_UNITS = 1_000


class CostEstimate(BaseModel):
    model_config = ConfigDict(frozen=True)

    estimated: bool
    task_count: int
    estimated_output_images: int
    estimated_partial_images: int
    estimated_prompt_tokens: int
    estimated_image_token_units: int
    estimated_total_token_units: int
    cost_usd: Optional[float]
    note: str


class CostEstimator:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def estimate(self, planned: PlannedJob) -> CostEstimate:
        task_count = len(planned.tasks)
        prompt_tokens = sum(_estimate_text_tokens(task.rendered_prompt) for task in planned.tasks)
        output_images = task_count
        partial_images = task_count * self.config.image.partial_images
        image_token_units = output_images * _image_token_units_for_size(self.config.image.size)
        total_token_units = prompt_tokens + image_token_units

        return CostEstimate(
            estimated=True,
            task_count=task_count,
            estimated_output_images=output_images,
            estimated_partial_images=partial_images,
            estimated_prompt_tokens=prompt_tokens,
            estimated_image_token_units=image_token_units,
            estimated_total_token_units=total_token_units,
            cost_usd=None,
            note="Estimated token-unit estimate only; no USD pricing is included.",
        )


def _estimate_text_tokens(text: str) -> int:
    return max(1, ceil(len(text) / 4))


def _image_token_units_for_size(size: str) -> int:
    if size in _SIZE_IMAGE_TOKEN_UNITS:
        return _SIZE_IMAGE_TOKEN_UNITS[size]
    return _DEFAULT_IMAGE_TOKEN_UNITS


__all__ = ["CostEstimate", "CostEstimator"]
