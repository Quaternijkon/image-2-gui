from app.core.config import AppConfig
from app.core.task_planner import TaskPlanner
from app.core.output_planner import OutputPlanner


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


def test_task_planner_expands_image_tasks_for_each_requested_variant(tmp_path, make_image):
    image = make_image(tmp_path / "input" / "a.png")
    config = AppConfig(
        input={"mode": "edit", "input_dir": tmp_path / "input"},
        image={"n": 3},
        prompt={"template": "Edit {stem} {variant} {index}"},
        output={"output_dir": tmp_path / "out", "job_subdir_enabled": False},
    )

    planned = TaskPlanner(config).build()

    assert [task.task_id for task in planned.tasks] == ["000001", "000002", "000003"]
    assert [task.source_paths for task in planned.tasks] == [[image], [image], [image]]
    assert [task.rendered_prompt for task in planned.tasks] == [
        "Edit a v1 000001",
        "Edit a v2 000002",
        "Edit a v3 000003",
    ]
    assert [task.output_plan.final_path.name for task in planned.tasks] == [
        "a_gpt_v1.png",
        "a_gpt_v2.png",
        "a_gpt_v3.png",
    ]


def test_task_planner_keeps_invalid_image_as_validation_failed_task(tmp_path, make_image):
    make_image(tmp_path / "input" / "good.png")
    bad = tmp_path / "input" / "bad.png"
    bad.write_text("not an image", encoding="utf-8")
    config = AppConfig(
        input={"input_dir": tmp_path / "input"},
        prompt={"template": "Edit {stem}"},
        output={"output_dir": tmp_path / "out", "job_subdir_enabled": False},
    )

    planned = TaskPlanner(config).build()

    assert [task.task_id for task in planned.tasks] == ["000001", "000002"]
    invalid_task = planned.tasks[0]
    assert invalid_task.source_paths == [bad]
    assert invalid_task.status == "validation_failed"
    assert invalid_task.input_image.width == 0
    assert invalid_task.input_image.height == 0
    assert invalid_task.output_plan.final_path == planned.job.final_dir / "bad_gpt_v1.png"
    assert any(issue.code == "invalid_image" for issue in invalid_task.input_image.issues)


def test_task_planner_reserves_output_paths_for_duplicate_stems(tmp_path, make_image):
    make_image(tmp_path / "input" / "a" / "same.png")
    make_image(tmp_path / "input" / "b" / "same.png")
    config = AppConfig(
        input={"input_dir": tmp_path / "input", "recursive": True},
        prompt={"template": "Edit {stem}"},
        output={
            "output_dir": tmp_path / "out",
            "job_subdir_enabled": False,
            "filename_template": "{stem}.{ext}",
        },
        execution={"overwrite_policy": "append_counter"},
    )

    planned = TaskPlanner(config).build()

    assert [task.output_plan.final_path.name for task in planned.tasks] == [
        "same.png",
        "same_2.png",
    ]


def test_task_planner_reserves_generate_outputs_when_template_omits_variant(tmp_path):
    config = AppConfig(
        input={"mode": "generate", "input_dir": None},
        image={"n": 3},
        prompt={"template": "Generate {index}"},
        output={
            "output_dir": tmp_path / "out",
            "job_subdir_enabled": False,
            "filename_template": "{stem}.{ext}",
        },
        execution={"overwrite_policy": "append_counter"},
    )

    planned = TaskPlanner(config).build()

    assert [task.output_plan.final_path.name for task in planned.tasks] == [
        "generate.png",
        "generate_2.png",
        "generate_3.png",
    ]


def test_task_planner_defers_job_artifacts_until_scan_and_prompt_render_succeed(tmp_path):
    output_dir = tmp_path / "out"
    missing_input = tmp_path / "missing"
    config = AppConfig(
        input={"mode": "edit", "input_dir": missing_input},
        prompt={"template": "Edit {stem}"},
        output={"output_dir": output_dir, "job_subdir_enabled": False},
    )

    try:
        TaskPlanner(config).build()
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("missing edit input should fail")

    assert not output_dir.exists()
