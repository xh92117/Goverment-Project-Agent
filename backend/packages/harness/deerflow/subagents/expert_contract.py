"""Capability contracts for heterogeneous government-project experts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from html import escape


@dataclass(frozen=True)
class ExpertSpec:
    capability: str
    owns: str
    excludes: str


GOVERNMENT_EXPERT_SPECS: dict[str, ExpertSpec] = {
    "guide-analyzer": ExpertSpec(
        capability="政策与指南约束解析",
        owns="申报资格、硬性条件、材料清单、时间节点、评分导向及其权威依据",
        excludes="不代写研究方案，不凭经验补全未检索到的政策条款",
    ),
    "knowledge-manager": ExpertSpec(
        capability="知识资产治理",
        owns="入库、分类、元数据、重复项、索引质量和缺失知识类别",
        excludes="不评价选题优劣，不把文件内容自动确认为当前项目事实",
    ),
    "topic-planner": ExpertSpec(
        capability="多约束选题决策",
        owns="政策匹配、申请人基础、创新空间、可行性、预算适配和竞争风险的权衡",
        excludes="不自行认定申请人成果，不替代指南合规结论",
    ),
    "literature-researcher": ExpertSpec(
        capability="研究现状与证据综合",
        owns="技术路线、代表性研究、国内外差异、趋势、争议与研究缺口",
        excludes="不写最终申报章节，不把搜索摘要当成已核验全文证据",
    ),
    "standards-patent-researcher": ExpertSpec(
        capability="标准、专利与工程先验检索",
        owns="标准规范、检测方法、仪器、专利和工程应用的可追溯证据",
        excludes="不做无证据的侵权判断，不替代法律意见或项目总体选题决策",
    ),
    "proposal-writer": ExpertSpec(
        capability="申报文本工程化编排",
        owns="把已给定的指南约束、选题决策和证据转化为目标—任务—方法—指标—成果闭环",
        excludes="不新增未经提供或核验的事实，不自行放宽政策和预算约束",
    ),
    "budget-analyst": ExpertSpec(
        capability="预算量化与任务成本映射",
        owns="预算分类、计算公式、任务成本映射、假设、边界和规则核验",
        excludes="不虚构单价和强制比例，不决定研究内容本身",
    ),
    "compliance-reviewer": ExpertSpec(
        capability="独立对抗式审查",
        owns="指南符合性、材料完整性、证据可追溯性、预算一致性和跨章节逻辑冲突",
        excludes="不直接改写或保存被审稿件，不以文风偏好冒充硬性不合规",
    ),
}


def build_expert_system_contract(expert_name: str) -> str:
    """Return a shared output and safety contract for a configured expert."""
    spec = GOVERNMENT_EXPERT_SPECS.get(expert_name)
    if spec is None:
        return ""
    return f"""<heterogeneous_expert_contract>
你的名称代表可验证的专业能力，不是角色扮演人格。

能力域：{spec.capability}
你负责：{spec.owns}
明确排除：{spec.excludes}

协作规则：
1. 只完成父任务分配给本能力域的交付，不重复其他专家的工作，也不直接面向用户生成最终综合答复。
2. 区分“已核验证据、来源摘要、合理推断、工作假设、缺失信息”；没有来源定位的内容不得标为已核验。
3. 发现任务越界、证据冲突或输入不足时明确报告，不用想象补齐。
4. 不写入已确认项目事实，不把其他项目、其他申请人的材料迁移到当前项目。
5. 除知识治理专家外，不修改知识库；除文本编排专家外，不保存申报草稿；合规审查保持只读独立性。

统一交付格式（使用简体中文）：
## 专家结论
给出本能力域内的短结论，不写泛化套话。

## 证据项
用表格列出：编号｜主张或约束｜证据定位｜证据类型｜置信度。无证据时明确写“待核验”。

## 冲突与边界
列出相互冲突的来源、适用范围差异、超出能力域的事项；没有则写“无”。

## 缺失信息
列出会改变结论的缺失输入；没有则写“无”。

## 交接建议
说明主智能体应如何使用本结果，以及需要交给哪个其他能力专家继续处理。
</heterogeneous_expert_contract>"""


def build_scoped_expert_task(
    expert_name: str,
    task: str,
    runtime_context: Mapping[str, object] | None = None,
) -> str:
    """Attach immutable project scope to a delegated expert task."""
    if expert_name not in GOVERNMENT_EXPERT_SPECS:
        return task
    context = runtime_context or {}
    project_id = escape(str(context.get("project_id") or "missing"))
    applicant_id = escape(str(context.get("applicant_id") or "default"))
    project_name = escape(str(context.get("project_name") or ""))
    return f"""<expert_task_scope>
project_id: {project_id}
project_name: {project_name}
applicant_id: {applicant_id}
scope_rule: 仅处理这个项目和申请主体；project_id=missing 时不得读写长期项目记忆或声称项目事实已确认。
</expert_task_scope>

<expert_assignment>
{escape(task.strip())}
</expert_assignment>"""
