from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.core.config import AppConfig
from app.core.errors import classify_exception
from app.core.models import TaskPlan


@dataclass(frozen=True)
class CompletedImage:
    b64_json: str
    usage: dict[str, Any] | None = None


@dataclass(frozen=True)
class PartialImage:
    index: int
    b64_json: str


ImageClientResult = list[CompletedImage | PartialImage]


class ImageClient(Protocol):
    async def run_task(self, task: TaskPlan) -> ImageClientResult:
        ...


class OpenAIImageClient:
    def __init__(self, config: AppConfig, *, sdk_client: Any | None = None) -> None:
        self.config = config
        self._sdk_client = sdk_client

    async def run_task(self, task: TaskPlan) -> ImageClientResult:
        try:
            if task.mode == "generate":
                return await self._generate(task)
            return await self._edit(task)
        except Exception as exc:
            raise classify_exception(exc) from exc

    @property
    def sdk_client(self) -> Any:
        if self._sdk_client is None:
            from openai import AsyncOpenAI

            self._sdk_client = AsyncOpenAI()
        return self._sdk_client

    async def _generate(self, task: TaskPlan) -> ImageClientResult:
        params = self._base_params(task)
        if self.config.image.stream:
            response = await self.sdk_client.images.generate(**params)
            return await _collect_stream(response)
        response = await self.sdk_client.images.generate(**params)
        return _collect_non_stream(response)

    async def _edit(self, task: TaskPlan) -> ImageClientResult:
        params = self._base_params(task)
        handles = []
        try:
            for source_path in task.source_paths:
                handle = source_path.open("rb")
                handles.append(handle)
            params["image"] = handles
            if task.mask_path is not None:
                mask = task.mask_path.open("rb")
                handles.append(mask)
                params["mask"] = mask
            if self.config.image.stream:
                response = await self.sdk_client.images.edit(**params)
                return await _collect_stream(response)
            response = await self.sdk_client.images.edit(**params)
            return _collect_non_stream(response)
        finally:
            for handle in handles:
                handle.close()

    def _base_params(self, task: TaskPlan) -> dict[str, Any]:
        image_config = self.config.image
        params: dict[str, Any] = {
            "model": self.config.api.model,
            "prompt": task.rendered_prompt,
            "size": image_config.size,
            "quality": image_config.quality,
            "output_format": image_config.output_format,
            "background": image_config.background,
            "moderation": image_config.moderation,
            "n": 1,
            "timeout": self.config.execution.timeout_seconds,
        }
        if image_config.output_compression is not None and image_config.output_format != "png":
            params["output_compression"] = image_config.output_compression
        if image_config.stream:
            params["stream"] = True
            if image_config.partial_images:
                params["partial_images"] = image_config.partial_images
        return params


class DeterministicMockImageClient:
    def __init__(self, *, b64_json: str | None = None) -> None:
        self.b64_json = b64_json or (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
        )

    async def run_task(self, task: TaskPlan) -> ImageClientResult:
        return [CompletedImage(b64_json=self.b64_json, usage={"mock": True})]


def _collect_non_stream(response: Any) -> ImageClientResult:
    usage = _as_dict(getattr(response, "usage", None))
    results: ImageClientResult = []
    for item in getattr(response, "data", []) or []:
        b64_json = _get_value(item, "b64_json")
        if b64_json:
            results.append(CompletedImage(b64_json=str(b64_json), usage=usage))
    return results


async def _collect_stream(response: Any) -> ImageClientResult:
    results: ImageClientResult = []
    async for event in response:
        event_type = str(_get_value(event, "type") or "")
        b64_json = _get_value(event, "b64_json") or _get_value(event, "partial_image_b64")
        if not b64_json:
            continue
        if "partial" in event_type:
            index = _get_value(event, "partial_image_index")
            if index is None:
                index = _get_value(event, "index") or len([r for r in results if isinstance(r, PartialImage)])
            results.append(PartialImage(index=int(index), b64_json=str(b64_json)))
        elif "completed" in event_type or "complete" in event_type:
            results.append(CompletedImage(b64_json=str(b64_json), usage=_as_dict(_get_value(event, "usage"))))
    return results


def _get_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _as_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {"value": value}


__all__ = [
    "CompletedImage",
    "DeterministicMockImageClient",
    "ImageClient",
    "ImageClientResult",
    "OpenAIImageClient",
    "PartialImage",
]
