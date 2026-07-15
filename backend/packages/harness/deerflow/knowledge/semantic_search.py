"""Lightweight semantic query expansion for declaration knowledge search."""

from __future__ import annotations

from collections.abc import Iterable

from deerflow.knowledge.schemas import KnowledgeIndexSearchRequest

_SECTION_EXPANSION_RULES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("国内外研究现状", "研究现状", "文献综述", "技术综述", "发展趋势", "研究动态", "state of the art", "literature review", "review"),
        ("domestic_foreign_status", "国内外研究现状", "研究现状", "文献综述", "发展趋势"),
    ),
    (
        ("研究内容", "主要内容", "研究任务", "研究目标", "关键科学问题", "解决什么问题", "research content", "objectives"),
        ("research_content", "主要研究内容", "研究目标", "关键科学问题", "研究任务"),
    ),
    (
        ("技术方案", "研究方案", "实施方案", "实验方案", "试验方案", "可行性", "technical solution", "implementation plan"),
        ("technical_solution", "技术方案", "研究方案", "实施方案", "可行性分析"),
    ),
    (
        ("技术路线", "路线图", "实施路径", "流程图", "怎么做", "如何实现", "technical route", "roadmap"),
        ("technical_route", "技术路线", "实施路径", "路线图", "关键步骤"),
    ),
    (
        ("创新点", "创新性", "特色", "先进性", "novelty", "innovation"),
        ("innovation_points", "创新点", "特色与创新", "先进性"),
    ),
    (
        ("研究基础", "工作基础", "前期基础", "已有基础", "已有条件", "research basis", "foundation"),
        ("research_basis", "研究基础", "工作基础", "前期基础", "已有条件"),
    ),
    (
        ("预期成果", "成果形式", "考核指标", "验收指标", "expected outputs", "deliverables"),
        ("expected_outputs", "预期成果", "成果形式", "考核指标"),
    ),
    (
        ("团队成果", "代表性成果", "论文", "专利", "软著", "获奖", "team achievements", "publications", "patents"),
        ("team_achievements", "团队成果", "代表性成果", "论文", "专利", "软著"),
    ),
    (
        ("预算", "经费", "预算依据", "经费预算", "经费说明", "budget", "funding"),
        ("budget_basis", "预算依据", "经费预算", "预算说明"),
    ),
    (
        ("申报条件", "申报要求", "申请资格", "申报资格", "申报对象", "eligibility", "requirements"),
        ("application_requirements", "申报条件", "申报要求", "申请资格"),
    ),
    (
        ("参考文献", "标准", "规范", "指南", "管理办法", "references", "standards"),
        ("references", "参考文献", "标准规范", "指南", "管理办法"),
    ),
    (
        ("立项依据", "研究意义", "应用前景", "背景意义", "background", "significance"),
        ("background_significance", "立项依据", "研究意义", "应用前景"),
    ),
)

_DOMAIN_EXPANSION_RULES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("路基", "填方", "压实度", "回弹模量", "落球", "subgrade"), ("路基工程", "填方施工质量", "路基质量评估")),
    (("隧洞", "隧道", "衬砌", "地质雷达", "tunnel"), ("隧洞检测", "隧道检测", "衬砌检测")),
    (("机器人", "无人车", "自动巡检", "robot"), ("机器人检测", "智能巡检", "自动化检测")),
    (("视觉", "图像", "缺陷检测", "机器视觉", "vision"), ("工业视觉", "机器视觉", "缺陷检测")),
    (("桥梁", "健康监测", "振动", "bridge"), ("桥梁工程", "桥梁健康监测", "结构健康监测")),
)

_PROJECT_EXPANSION_RULES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("重点研发", "科技计划", "科研项目", "research project"), ("重点研发", "科研项目申报", "科技计划项目")),
    (("揭榜挂帅", "榜单", "攻关"), ("揭榜挂帅", "关键核心技术攻关")),
    (("高企", "高新技术企业"), ("高新技术企业", "企业研发项目")),
)

_MAX_EXPANSIONS = 40


def _append_unique(values: list[str], additions: Iterable[str]) -> None:
    seen = {value.casefold() for value in values}
    for addition in additions:
        normalized = addition.strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        values.append(normalized)


def _matches_any(query: str, triggers: Iterable[str]) -> bool:
    return any(trigger.casefold() in query for trigger in triggers)


def expand_knowledge_query(query: str) -> str:
    """Expand natural declaration-writing intents into indexed chapter terms."""

    stripped = query.strip()
    if not stripped:
        return query

    folded = stripped.casefold()
    expansions: list[str] = []
    for rules in (_SECTION_EXPANSION_RULES, _DOMAIN_EXPANSION_RULES, _PROJECT_EXPANSION_RULES):
        for triggers, terms in rules:
            if _matches_any(folded, triggers):
                _append_unique(expansions, terms)

    if not expansions:
        return query
    return " ".join([stripped, *expansions[:_MAX_EXPANSIONS]])


def expand_knowledge_index_search_request(request: KnowledgeIndexSearchRequest) -> KnowledgeIndexSearchRequest:
    """Return a search request with an expanded query while preserving filters."""

    expanded_query = expand_knowledge_query(request.query)
    if expanded_query == request.query:
        return request
    return request.model_copy(update={"query": expanded_query})
