from __future__ import annotations

import json
from types import SimpleNamespace

from langchain_core.messages import AIMessage

from deerflow.config.knowledge_retrieval_config import KnowledgeChunkingConfig
from deerflow.knowledge.semantic_chunking import (
    KnowledgeChunkingSection,
    KnowledgeChunkingUnit,
    KnowledgeSemanticChunkPlanner,
)


class _StubModel:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.messages: list[object] = []

    def invoke(self, messages: object) -> AIMessage:
        self.messages.append(messages)
        return AIMessage(content=json.dumps(self.payload, ensure_ascii=False))


def test_semantic_chunking_is_enabled_by_default() -> None:
    assert KnowledgeChunkingConfig().enabled is True


def _app_config(chunking: KnowledgeChunkingConfig, *, selected_model: str = "selected-build-model"):
    return SimpleNamespace(
        knowledge_retrieval=SimpleNamespace(chunking=chunking),
        knowledge_model=selected_model,
        knowledge_image_model="legacy-vision-model",
        models=[SimpleNamespace(name=selected_model), SimpleNamespace(name="legacy-vision-model")],
    )


def _section() -> KnowledgeChunkingSection:
    return KnowledgeChunkingSection(
        section_id="section-1",
        heading="国内外研究现状",
        heading_path=("立项依据", "国内外研究现状"),
        units=(
            KnowledgeChunkingUnit(unit_id=1, text="第一段介绍国内研究现状。"),
            KnowledgeChunkingUnit(unit_id=2, text="第二段继续分析国内技术路线。"),
            KnowledgeChunkingUnit(unit_id=3, text="第三段转向国外研究进展。"),
        ),
    )


def test_semantic_chunk_planner_uses_model_selected_on_knowledge_page() -> None:
    chunking = KnowledgeChunkingConfig(
        enabled=True,
        minimum_section_chars=1,
        minimum_chunk_chars=1,
        target_chunk_chars=80,
        maximum_chunk_chars=200,
        unit_max_chars=80,
        max_prompt_chars=4_000,
    )
    model = _StubModel(
        {
            "plans": [
                {
                    "section_id": "section-1",
                    "chunks": [
                        {
                            "start_unit": 1,
                            "end_unit": 2,
                            "primary_section": "domestic_foreign_status",
                            "secondary_sections": ["research_content"],
                            "content_role": "background",
                            "keywords": ["国内研究现状", "技术路线"],
                            "technical_terms": ["技术路线"],
                        },
                        {"start_unit": 3, "end_unit": 3},
                    ],
                }
            ]
        }
    )
    factory_calls: list[dict[str, object]] = []

    def factory(**kwargs):
        factory_calls.append(kwargs)
        return model

    planner = KnowledgeSemanticChunkPlanner(app_config=_app_config(chunking), model_factory=factory)
    result = planner.plan([_section()])

    assert factory_calls[0]["name"] == "selected-build-model"
    assert factory_calls[0]["temperature"] == 0.0
    assert [(item.start_unit, item.end_unit) for item in result.plans["section-1"]] == [(1, 2), (3, 3)]
    first_chunk = result.plans["section-1"][0]
    assert first_chunk.primary_section == "domestic_foreign_status"
    assert first_chunk.secondary_sections == ("research_content",)
    assert first_chunk.content_role == "background"
    assert first_chunk.keywords == ("国内研究现状", "技术路线")
    assert result.model_name == "selected-build-model"
    assert result.calls == 1
    assert result.fallback_sections == 0
    assert model.messages


def test_semantic_chunk_planner_rejects_incomplete_model_plan_and_falls_back() -> None:
    chunking = KnowledgeChunkingConfig(
        enabled=True,
        minimum_section_chars=1,
        minimum_chunk_chars=1,
        target_chunk_chars=80,
        maximum_chunk_chars=200,
        unit_max_chars=80,
        max_prompt_chars=4_000,
    )
    model = _StubModel(
        {
            "plans": [
                {
                    "section_id": "section-1",
                    "chunks": [{"start_unit": 1, "end_unit": 1}, {"start_unit": 3, "end_unit": 3}],
                }
            ]
        }
    )
    planner = KnowledgeSemanticChunkPlanner(app_config=_app_config(chunking), model_factory=lambda **_: model)

    result = planner.plan([_section()])

    assert result.plans == {}
    assert result.fallback_sections == 1
    assert any("不连续" in warning or "未完整覆盖" in warning for warning in result.warnings)


def test_disabled_semantic_chunk_planner_never_creates_model() -> None:
    chunking = KnowledgeChunkingConfig(enabled=False)

    def fail_factory(**_kwargs):
        raise AssertionError("disabled planner must not create a model")

    planner = KnowledgeSemanticChunkPlanner(app_config=_app_config(chunking), model_factory=fail_factory)
    result = planner.plan([_section()])

    assert result.plans == {}
    assert result.calls == 0
    assert result.warnings == []


def test_unavailable_semantic_chunk_model_falls_back_without_raising() -> None:
    chunking = KnowledgeChunkingConfig(
        enabled=True,
        minimum_section_chars=1,
        minimum_chunk_chars=1,
        target_chunk_chars=80,
        maximum_chunk_chars=200,
        unit_max_chars=80,
        max_prompt_chars=4_000,
    )

    def unavailable_factory(**_kwargs):
        raise RuntimeError("provider timeout")

    planner = KnowledgeSemanticChunkPlanner(app_config=_app_config(chunking), model_factory=unavailable_factory)
    result = planner.plan([_section()])

    assert result.plans == {}
    assert result.fallback_sections == 1
    assert result.calls == 0
    assert any("回退规则分块" in warning and "provider timeout" in warning for warning in result.warnings)


def test_semantic_chunk_planner_does_not_use_legacy_image_model_as_build_selection() -> None:
    chunking = KnowledgeChunkingConfig(
        enabled=True,
        minimum_section_chars=1,
        minimum_chunk_chars=1,
        target_chunk_chars=80,
        maximum_chunk_chars=200,
        unit_max_chars=80,
        max_prompt_chars=4_000,
    )
    app_config = _app_config(chunking, selected_model="")

    def fail_factory(**_kwargs):
        raise AssertionError("legacy image selection must not be used for semantic chunking")

    result = KnowledgeSemanticChunkPlanner(app_config=app_config, model_factory=fail_factory).plan([_section()])

    assert result.plans == {}
    assert result.fallback_sections == 1
    assert any("尚未选择构建模型" in warning for warning in result.warnings)
