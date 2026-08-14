from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import AIMessage

from deerflow.config.knowledge_retrieval_config import KnowledgeChunkingConfig
from deerflow.knowledge import generator as knowledge_generator
from deerflow.knowledge import organizer as knowledge_organizer
from deerflow.knowledge import storage as knowledge_storage
from deerflow.knowledge.organizer import KnowledgeOrganizeOptions, organize_incoming_files
from deerflow.knowledge.semantic_chunking import KnowledgeSemanticChunkPlanner
from deerflow.knowledge.semantic_classification import KnowledgeSemanticSourceClassifier, KnowledgeSourceClassification


def _app_config(chunking: KnowledgeChunkingConfig, *, selected_model: str = "selected-build-model") -> SimpleNamespace:
    return SimpleNamespace(
        knowledge_retrieval=SimpleNamespace(chunking=chunking),
        knowledge_model=selected_model,
        models=[SimpleNamespace(name=selected_model)],
    )


def test_flat_mineru_headings_are_repaired_from_numbering() -> None:
    content = (
        "# 混凝土结构激光检测技术体系\n\n"
        "# 本报告对应设备\n\n设备说明。\n\n"
        "## 第 2章 ILE法检测原理\n\n"
        "## 2.1 背景及基本概念\n\n背景。\n\n"
        "## 2.1.1 激光测振的基本理论\n\n理论。\n\n"
        "## 2.1.2 激光检测与弹性波检测的异同\n\n异同。\n\n"
        "## 1）传感器的耦合方式\n\n耦合方式会影响固有频率。\n\n"
        "## 第 3章 验证试验\n\n"
        "## 3.1 室内对比验证试验\n\n"
        "## 3.1.1 混凝土模型\n\n模型试验。\n"
    )

    blocks = knowledge_generator._structured_heading_blocks(content)
    paths = {block.heading: block.heading_path for block in blocks}

    assert paths["2.1.2 激光检测与弹性波检测的异同"] == (
        "混凝土结构激光检测技术体系",
        "第 2章 ILE法检测原理",
        "2.1 背景及基本概念",
        "2.1.2 激光检测与弹性波检测的异同",
    )
    assert paths["1）传感器的耦合方式"][-2:] == (
        "2.1.2 激光检测与弹性波检测的异同",
        "1）传感器的耦合方式",
    )
    assert "本报告对应设备" not in paths["3.1.1 混凝土模型"]


def test_model_plans_unmerged_adjacent_short_sections_before_rule_fallback() -> None:
    content = (
        "# 激光检测技术体系\n\n"
        "## 第 2章 ILE法检测原理\n\n"
        "## 2.1 背景及基本概念\n\n"
        + "激光拾振不需接触被测体，可以提高测试效率和一致性。" * 8
        + "\n\n## 2.1.1 激光测振的基本理论\n\n"
        + "激光测振的理论基于多普勒效应，通过频移计算表面质点振动。" * 5
        + "\n\n## 2.1.2 激光检测与弹性波检测的异同\n\n"
        + "两者都测试介质中弹性波的传播规律，主要区别在于耦合和共振。" * 4
        + "\n\n## 1）传感器的耦合方式\n\n"
        + "接触式传感器需要固定在被测体表面，耦合方式会影响固有频率。"
    )
    config = KnowledgeChunkingConfig()
    raw_candidates = knowledge_generator._build_semantic_chunk_candidates(content, "技术资料", config=config, merge_short=False)
    requests: list[dict[str, object]] = []

    class PlannerModel:
        def invoke(self, messages: list[object]) -> AIMessage:
            request = json.loads(messages[1].content.split("\n", 1)[1])
            requests.append(request)
            plans = []
            for section in request["sections"]:
                plans.append(
                    {
                        "section_id": section["section_id"],
                        "chunks": [
                            {
                                "start_unit": 1,
                                "end_unit": len(section["units"]),
                                "primary_section": "background_significance",
                                "secondary_sections": [],
                                "content_role": "background",
                                "keywords": ["激光测振"],
                                "technical_terms": ["多普勒效应"],
                                "methods": [],
                                "research_objects": ["被测体"],
                            }
                        ],
                    }
                )
            return AIMessage(content=json.dumps({"plans": plans}, ensure_ascii=False))

    planner = KnowledgeSemanticChunkPlanner(app_config=_app_config(config), model_factory=lambda **_: PlannerModel())
    refined, warnings = knowledge_generator._refine_candidates_with_model(
        raw_candidates,
        planner=planner,
        source_title="激光检测技术体系",
        source_category="技术资料",
    )
    published = knowledge_generator._postprocess_short_candidates(refined, config=config)

    assert requests
    assert any(len(section["source_anchors"]) > 1 for request in requests for section in request["sections"])
    assert any(candidate.chunking_strategy == "llm_semantic" for candidate in published)
    assert any("1）传感器的耦合方式" in candidate.source_anchors for candidate in published)
    assert not warnings


def test_semantic_source_classifier_is_allow_listed_and_uses_selected_model() -> None:
    calls: list[dict[str, object]] = []

    class ClassifierModel:
        def invoke(self, messages: list[object]) -> AIMessage:
            calls.append(json.loads(messages[1].content.split("\n", 1)[1]))
            return AIMessage(
                content=json.dumps(
                    {
                        "category": "技术资料",
                        "domain": "隧洞检测",
                        "confidence": 0.94,
                        "reason": "内容为检测原理和验证试验，不是项目申报书。",
                    },
                    ensure_ascii=False,
                )
            )

    classifier = KnowledgeSemanticSourceClassifier(
        app_config=_app_config(KnowledgeChunkingConfig()),
        model_factory=lambda **_: ClassifierModel(),
    )
    result = classifier.classify(
        source_path="_incoming/混凝土结构激光检测技术体系.pdf",
        title="混凝土结构激光检测技术体系",
        headings=("第2章 ILE法检测原理", "第3章 验证试验"),
        preview="利用多普勒激光替代拾振传感器，并进行轨道板和隧道模型对比验证。",
        allowed_categories=("未分类", "历史申报书", "技术资料", "团队成果"),
        allowed_domains=("通用", "无损检测", "隧洞检测"),
        rule_category="未分类",
        rule_domain="隧洞检测",
    )

    assert result == KnowledgeSourceClassification(
        category="技术资料",
        domain="隧洞检测",
        confidence=0.94,
        reason="内容为检测原理和验证试验，不是项目申报书。",
        model_name="selected-build-model",
    )
    assert calls[0]["allowed_categories"] == ["未分类", "历史申报书", "技术资料", "团队成果"]


def test_organizer_uses_semantic_classification_only_for_unresolved_dimension(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "knowledge_base"
    source = root / "_incoming" / "混凝土结构激光检测技术体系.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "# 混凝土结构激光检测技术体系\n\n## ILE冲击回波法检测原理\n\n利用激光拾振进行轨道板和隧道模型对比验证。",
        encoding="utf-8",
    )
    monkeypatch.setattr(knowledge_storage, "_knowledge_root_path", lambda *, user_id=None: root)
    monkeypatch.setattr(knowledge_organizer, "_knowledge_root_path", lambda *, user_id=None: root)

    class StubClassifier:
        model_name = "selected-build-model"

        def classify(self, **_kwargs) -> KnowledgeSourceClassification:
            return KnowledgeSourceClassification(
                category="技术资料",
                domain="隧洞检测",
                confidence=0.92,
                reason="技术原理与验证试验资料",
                model_name=self.model_name,
            )

    report = organize_incoming_files(KnowledgeOrganizeOptions(), user_id="alice", semantic_classifier=StubClassifier())

    organized = report.files[0]
    assert organized.target_path == "技术资料/隧洞检测/混凝土结构激光检测技术体系.md"
    assert organized.category_strategy == "llm_semantic"
    assert organized.domain_strategy == "rules"
    assert organized.classification_model == "selected-build-model"
    assert (root / organized.target_path).exists()
