from app.core.config import AppConfig
from app.core.file_scanner import scan_input_images
from app.core.models import InputImage, JobLayout, PlannedJob, TaskPlan
from app.core.output_planner import OutputPlanner
from app.core.prompt_renderer import PromptRenderer


class TaskPlanner:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def build(self) -> PlannedJob:
        output_planner = OutputPlanner(self.config)
        job = output_planner.create_job_layout()
        if self.config.input.mode == "generate":
            tasks = self._build_generate_tasks(output_planner, job)
            return PlannedJob(job=job, tasks=tasks, issues=[])

        scan = scan_input_images(self.config.input)
        tasks = self._build_image_tasks(scan.images, output_planner, job)
        return PlannedJob(job=job, tasks=tasks, issues=scan.issues)

    def _build_generate_tasks(self, output_planner: OutputPlanner, job: JobLayout) -> list[TaskPlan]:
        tasks: list[TaskPlan] = []
        for index in range(1, self.config.image.n + 1):
            task_id = f"{index:06d}"
            prompt = self._render_prompt(
                stem="generate",
                index=task_id,
                variant=f"v{index}",
            )
            task = TaskPlan(
                task_id=task_id,
                mode="generate",
                source_paths=[],
                mask_path=None,
                rendered_prompt=prompt,
                output_plan=None,
            )
            task.output_plan = output_planner.plan_variant_output(job, task, variant=index)
            tasks.append(task)
        return tasks

    def _build_image_tasks(
        self, images: list[InputImage], output_planner: OutputPlanner, job: JobLayout
    ) -> list[TaskPlan]:
        tasks: list[TaskPlan] = []
        for index, image in enumerate(images, start=1):
            task_id = f"{index:06d}"
            prompt = self._render_prompt(
                stem=image.path.stem,
                index=task_id,
                variant="v1",
            )
            task = TaskPlan(
                task_id=task_id,
                mode=self.config.input.mode,
                source_paths=[image.path],
                mask_path=image.mask_path,
                rendered_prompt=prompt,
                output_plan=None,
                input_image=image,
                status="validation_failed"
                if image.validation_status == "validation_failed"
                else "queued",
            )
            task.output_plan = output_planner.plan_variant_output(job, task, variant=1)
            tasks.append(task)
        return tasks

    def _render_prompt(self, *, stem: str, index: str, variant: str) -> str:
        renderer = PromptRenderer(
            variables_enabled=self.config.prompt.variables_enabled,
            context={
                "stem": stem,
                "index": index,
                "variant": variant,
                "quality": self.config.image.quality,
                "size": self.config.image.size,
                "date": "",
                "hash": "",
            },
        )
        return renderer.render(self.config.prompt.template)


__all__ = ["TaskPlanner", "PlannedJob"]
