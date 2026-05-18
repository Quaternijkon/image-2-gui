import pytest

from app.core.prompt_renderer import PromptRenderError, PromptRenderer


def test_prompt_renderer_replaces_known_variables():
    renderer = PromptRenderer(
        variables_enabled=True,
        context={
            "stem": "product_001",
            "index": 7,
            "variant": 2,
            "quality": "high",
            "size": "1024x1024",
            "date": "20260519",
            "hash": "abc123",
        },
    )

    assert (
        renderer.render("{stem} #{index} v{variant} {quality} {size} {date} {hash}")
        == "product_001 #7 v2 high 1024x1024 20260519 abc123"
    )


def test_prompt_renderer_fails_on_unknown_variable():
    renderer = PromptRenderer(variables_enabled=True, context={"stem": "product_001"})

    with pytest.raises(PromptRenderError, match="unknown prompt variable: missing"):
        renderer.render("Create {missing}")


def test_prompt_renderer_returns_template_unchanged_when_variables_disabled():
    renderer = PromptRenderer(variables_enabled=False, context={"stem": "product_001"})

    assert renderer.render("Create {stem} {missing}") == "Create {stem} {missing}"


def test_prompt_renderer_wraps_malformed_format_strings():
    renderer = PromptRenderer(variables_enabled=True, context={"stem": "product_001"})

    with pytest.raises(PromptRenderError, match="malformed prompt template"):
        renderer.render("Create {stem")
