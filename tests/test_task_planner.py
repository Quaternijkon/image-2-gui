from app.core.config import AppConfig
from app.core.task_planner import TaskPlanner


def test_task_planner_builds_edit_tasks_with_prompts_masks_and_outputs(tmp_path, make_image):
    first = make_image(tmp_path / "input" / "a.png")
    second = make_image(tmp_path / "input" / "b.png")
    mask_dir = tmp_path / "masks"
    first_mask = make_image(mask_dir / "a.png", mode="RGBA", color=(0, 0, 0, 128))
    make_image(mask_dir / "b.png", mode="RGB")
    config = AppConfig(
        input={"input_dir": tmp_path / "input", "mask_dir": mask_dir},
        prompt={"template": "Edit {stem} as {index}"},
        output={"output_dir": tmp_path / "out", "job_subdir_enabled": False},
    )

    planned = TaskPlanner(config).build()

    assert [task.task_id for task in planned.tasks] == ["000001", "000002"]
    assert [task.rendered_prompt for task in planned.tasks] == [
        "Edit a as 000001",
        "Edit b as 000002",
    ]
    assert planned.tasks[0].source_paths == [first]
    assert planned.tasks[0].mask_path == first_mask
    assert planned.tasks[0].status == "queued"
    assert planned.tasks[0].output_plan.final_path == planned.job.final_dir / "a_gpt_v1.png"
    assert planned.tasks[1].source_paths == [second]
    assert planned.tasks[1].status == "validation_failed"
    assert planned.tasks[1].output_plan.final_path == planned.job.final_dir / "b_gpt_v1.png"
    assert any(issue.code == "mask_missing_alpha" for issue in planned.issues)


def test_task_planner_builds_generate_tasks_without_input_dir(tmp_path):
    config = AppConfig(
        input={"mode": "generate", "input_dir": None},
        image={"n": 3},
        prompt={"template": "Generate {index} {stem}"},
        output={"output_dir": tmp_path / "out", "job_subdir_enabled": False},
    )

    planned = TaskPlanner(config).build()

    assert [task.task_id for task in planned.tasks] == ["000001", "000002", "000003"]
    assert [task.source_paths for task in planned.tasks] == [[], [], []]
    assert [task.rendered_prompt for task in planned.tasks] == [
        "Generate 000001 generate",
        "Generate 000002 generate",
        "Generate 000003 generate",
    ]
    assert [task.output_plan.final_path.name for task in planned.tasks] == [
        "generate_gpt_v1.png",
        "generate_gpt_v2.png",
        "generate_gpt_v3.png",
    ]
