from app.core.config import AppConfig
from app.core.cost_estimator import CostEstimator
from app.core.task_planner import TaskPlanner


def test_cost_estimator_marks_values_as_estimated_without_claiming_usd_pricing(tmp_path):
    config = AppConfig(
        input={"mode": "generate"},
        image={"n": 3, "partial_images": 2, "size": "1024x1024"},
        prompt={"template": "Generate a polished product image number {index}"},
        output={"output_dir": tmp_path / "out", "job_subdir_enabled": False},
    )
    planned = TaskPlanner(config).build()

    estimate = CostEstimator(config).estimate(planned)

    assert estimate.estimated is True
    assert estimate.task_count == 3
    assert estimate.estimated_output_images == 3
    assert estimate.estimated_partial_images == 6
    assert estimate.estimated_prompt_tokens > 0
    assert estimate.estimated_image_token_units > 0
    assert estimate.estimated_total_token_units >= estimate.estimated_prompt_tokens
    assert estimate.cost_usd is None
    assert "token-unit estimate" in estimate.note
