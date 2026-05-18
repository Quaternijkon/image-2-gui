from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.core.api_capabilities import get_model_capabilities


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApiConfig(StrictModel):
    provider: Literal["openai"] = "openai"
    api_type: Literal["image"] = "image"
    model: Literal["gpt-image-2"] = "gpt-image-2"
    api_key_source: str = "env"
    api_key: Optional[str] = Field(default=None, exclude=True, repr=False)

    @field_validator("api_key_source")
    @classmethod
    def api_key_source_must_be_safe_reference(cls, value: str) -> str:
        if value.startswith("sk-"):
            raise ValueError("api_key_source must reference a safe key source, not secret material")

        allowed_exact = {"env", "keyring", "windows_credential_manager", "none"}
        if value in allowed_exact:
            return value

        if value.startswith("env:") and len(value) > 4:
            env_name = value[4:]
            if env_name.replace("_", "").isalnum() and not env_name[0].isdigit():
                return value

        raise ValueError("api_key_source must reference a safe key source")


class InputConfig(StrictModel):
    mode: Literal["generate", "edit", "inpaint", "mask"] = "edit"
    input_dir: Optional[Path] = None
    recursive: bool = False
    extensions: list[str] = Field(default_factory=lambda: [".png", ".jpg", ".jpeg", ".webp"])
    mask_dir: Optional[Path] = None
    reference_grouping: Literal["one_task_per_image"] = "one_task_per_image"


class PromptConfig(StrictModel):
    template: str = "Describe the image to generate or edit."
    variables_enabled: bool = True
    csv_prompt_map: Optional[Path] = None

    @field_validator("template")
    @classmethod
    def template_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("prompt template must not be empty")
        return value


class ImageConfig(StrictModel):
    size: str = "auto"
    quality: str = "auto"
    output_format: str = "png"
    output_compression: Optional[int] = None
    background: str = "auto"
    moderation: Literal["auto", "low"] = "auto"
    n: int = Field(default=1, ge=1, le=10)
    stream: bool = False
    partial_images: int = 0
    save_partials: bool = False

    @field_validator("size")
    @classmethod
    def size_must_match_capabilities(cls, value: str) -> str:
        capabilities = get_model_capabilities("gpt-image-2")["size"]
        if value == "auto":
            return value

        if "x" not in value:
            raise ValueError("size must be 'auto' or a WxH string such as 1024x1024")

        try:
            width_text, height_text = value.lower().split("x", 1)
            width = int(width_text)
            height = int(height_text)
        except ValueError as exc:
            raise ValueError("size must be 'auto' or a WxH string such as 1024x1024") from exc

        if width <= 0 or height <= 0:
            raise ValueError("size edges must be positive")

        if width > capabilities["max_edge"] or height > capabilities["max_edge"]:
            raise ValueError(f"each size edge must be <= {capabilities['max_edge']}")

        multiple = capabilities["edge_multiple"]
        if width % multiple != 0 or height % multiple != 0:
            raise ValueError(f"each size edge must be a multiple of {multiple}")

        long_edge = max(width, height)
        short_edge = min(width, height)
        if long_edge / short_edge > capabilities["max_long_short_ratio"]:
            raise ValueError("long:short size ratio must be <= 3:1")

        pixels = width * height
        if pixels < capabilities["min_pixels"] or pixels > capabilities["max_pixels"]:
            raise ValueError(
                "total pixels must be between "
                f"{capabilities['min_pixels']} and {capabilities['max_pixels']}"
            )

        return f"{width}x{height}"

    @field_validator("partial_images")
    @classmethod
    def partial_images_must_match_capabilities(cls, value: int) -> int:
        bounds = get_model_capabilities("gpt-image-2")["partial_images"]
        if value < bounds["minimum"] or value > bounds["maximum"]:
            raise ValueError(
                f"partial_images must be between {bounds['minimum']} and {bounds['maximum']}"
            )
        return value

    @model_validator(mode="after")
    def image_options_must_match_capabilities(self) -> "ImageConfig":
        capabilities = get_model_capabilities("gpt-image-2")

        if self.output_format not in capabilities["output_formats"]:
            raise ValueError(
                "output_format must be one of " + ", ".join(capabilities["output_formats"])
            )

        if self.quality not in capabilities["qualities"]:
            raise ValueError("quality must be one of " + ", ".join(capabilities["qualities"]))

        if self.background not in capabilities["backgrounds"]:
            raise ValueError("transparent background is not supported for gpt-image-2")

        compression_bounds = capabilities["output_compression"]
        if self.output_compression is not None:
            if self.output_format not in capabilities["compression_formats"]:
                raise ValueError("output_compression only applies to jpeg/webp output")
            if (
                self.output_compression < compression_bounds["minimum"]
                or self.output_compression > compression_bounds["maximum"]
            ):
                raise ValueError("output_compression must be 0-100")

        return self


class ExecutionConfig(StrictModel):
    concurrency: int = Field(default=2, ge=1, le=8)
    max_retries: int = Field(default=2, ge=0, le=5)
    timeout_seconds: int = Field(default=240, ge=30, le=600)
    failure_policy: Literal["continue", "stop"] = "continue"
    overwrite_policy: Literal["skip_existing", "overwrite", "append_counter", "new_job_dir"] = (
        "skip_existing"
    )


class OutputConfig(StrictModel):
    output_dir: Optional[Path] = None
    job_subdir_enabled: bool = True
    filename_template: str = "{stem}_gpt_{variant}.{ext}"
    save_manifest: bool = True
    save_logs: bool = True
    save_config_snapshot: bool = True


class AppConfig(StrictModel):
    version: int = 1
    api: ApiConfig = Field(default_factory=ApiConfig)
    input: InputConfig = Field(default_factory=InputConfig)
    prompt: PromptConfig = Field(default_factory=PromptConfig)
    image: ImageConfig = Field(default_factory=ImageConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)


__all__ = [
    "ApiConfig",
    "AppConfig",
    "ExecutionConfig",
    "ImageConfig",
    "InputConfig",
    "OutputConfig",
    "PromptConfig",
    "ValidationError",
]
