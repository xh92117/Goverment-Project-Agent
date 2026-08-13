from pathlib import Path

import yaml

from deerflow.skills.parser import parse_skill_file
from deerflow.skills.types import SkillCategory

REPO_ROOT = Path(__file__).resolve().parents[2]
GOV_SKILL_NAMES = {
    "gov-proposal-knowledge-incremental-update",
    "gov-proposal-topic-planning",
    "gov-proposal-literature-review",
    "gov-proposal-research-plan-writing",
    "gov-proposal-budget-planning",
    "gov-proposal-compliance-review",
    "gov-proposal-web-research",
}


def test_government_project_skills_keep_required_runtime_tools_available():
    skills_root = REPO_ROOT / "skills" / "public"
    parsed = []
    for name in GOV_SKILL_NAMES:
        skill = parse_skill_file(skills_root / name / "SKILL.md", SkillCategory.PUBLIC)
        assert skill is not None
        parsed.append(skill)

    allowed_union = set()
    for skill in parsed:
        assert skill.allowed_tools is not None
        allowed_union.update(skill.allowed_tools)

    assert {
        "ls",
        "read_file",
        "glob",
        "grep",
        "knowledge_search_index",
        "knowledge_read_file",
        "knowledge_search_evidence",
        "knowledge_read_evidence",
        "knowledge_list_images",
        "knowledge_incremental_update",
        "proposal_save_markdown",
        "present_files",
        "view_image",
        "update_agent",
        "web_search",
        "web_fetch",
        "web_extract",
        "task",
    } <= allowed_union


def test_custom_subagent_tools_survive_their_skill_policy():
    data = yaml.safe_load((REPO_ROOT / "config.example.yaml").read_text(encoding="utf-8"))
    skills_root = REPO_ROOT / "skills" / "public"

    for agent_name, agent_config in data["subagents"]["custom_agents"].items():
        configured_tools = agent_config.get("tools") or []
        assert len(configured_tools) == len(set(configured_tools)), f"{agent_name} declares duplicate tools"

        allowed_tools: set[str] = set()
        for skill_name in agent_config.get("skills") or []:
            skill = parse_skill_file(skills_root / skill_name / "SKILL.md", SkillCategory.PUBLIC)
            assert skill is not None, f"{agent_name} references missing skill {skill_name}"
            assert skill.allowed_tools is not None
            allowed_tools.update(skill.allowed_tools)

        assert set(configured_tools) <= allowed_tools, (
            f"{agent_name} tools removed by skill allowed-tools policy: "
            f"{sorted(set(configured_tools) - allowed_tools)}"
        )


def test_government_project_agent_template_enables_web_tool_group():
    data = yaml.safe_load(
        (REPO_ROOT / "configs" / "government-project-declaration.agent.example.yaml").read_text(encoding="utf-8")
    )

    assert {"filesystem", "web"} <= set(data["tool_groups"])


def test_government_project_existing_configs_receive_required_web_group():
    from types import SimpleNamespace

    from deerflow.agents.lead_agent.agent import _effective_tool_groups

    legacy_config = SimpleNamespace(tool_groups=["filesystem"])

    assert _effective_tool_groups("government-project-declaration", legacy_config) == ["filesystem", "web"]
    assert _effective_tool_groups("other-agent", legacy_config) == ["filesystem"]


def test_root_config_declares_government_project_custom_subagents():
    data = yaml.safe_load((REPO_ROOT / "config.yaml").read_text(encoding="utf-8"))
    custom_agents = data["subagents"]["custom_agents"]

    expected = {
        "guide-analyzer",
        "knowledge-manager",
        "topic-planner",
        "literature-researcher",
        "standards-patent-researcher",
        "proposal-writer",
        "budget-analyst",
        "compliance-reviewer",
    }
    assert expected <= set(custom_agents)
    assert "web_fetch" in custom_agents["guide-analyzer"]["tools"]
    assert "proposal_save_markdown" in custom_agents["proposal-writer"]["tools"]
    assert "web_search" in custom_agents["standards-patent-researcher"]["tools"]
    assert "patents" in custom_agents["standards-patent-researcher"]["description"].lower()
    assert data["subagents"]["agents"]["compliance-reviewer"]["model"] == "qwen-qwen3.7-plus"
    assert "proposal_save_markdown" not in custom_agents["compliance-reviewer"]["tools"]
    assert "web_search" not in custom_agents["proposal-writer"]["tools"]
    assert "read-only critic" in custom_agents["compliance-reviewer"]["description"]

    web_search = next(tool for tool in data["tools"] if tool["name"] == "web_search")
    assert web_search["use"] == "deerflow.community.hybrid_search.tools:web_search_tool"
    assert {"serper", "ddgs", "simple_web"} <= set(web_search["providers"])
    assert {"bing_cn", "baidu", "duckduckgo"} <= set(web_search["simple_web_engines"])
    assert web_search["official_first"] is True
    assert "gov.cn" in web_search["official_domains"]
    assert "cnipa.gov.cn" in web_search["official_domains"]
    assert "chinastandard.gov.cn" in web_search["official_domains"]
    assert "edu.cn" in web_search["official_domains"]
    assert "ac.cn" in web_search["official_domains"]
    assert web_search["cache_enabled"] is True
    assert web_search["cache_ttl_seconds"] == 900


def test_root_config_registers_prompted_filesystem_read_tools():
    data = yaml.safe_load((REPO_ROOT / "config.yaml").read_text(encoding="utf-8"))
    tools = {tool["name"]: tool for tool in data["tools"]}

    for name in ("ls", "read_file", "glob", "grep"):
        assert tools[name]["group"] == "filesystem"

    assert tools["ls"]["use"] == "deerflow.sandbox.tools:ls_tool"
    assert tools["read_file"]["use"] == "deerflow.sandbox.tools:read_file_tool"
    assert tools["glob"]["use"] == "deerflow.sandbox.tools:glob_tool"
    assert tools["grep"]["use"] == "deerflow.sandbox.tools:grep_tool"


def test_government_project_soul_requires_knowledge_synthesis():
    soul = (REPO_ROOT / "backend" / ".agent-base" / "agents" / "government-project-declaration" / "SOUL.md").read_text(encoding="utf-8")

    assert "Knowledge synthesis rules" in soul
    assert "Do not answer by concatenating retrieval snippets" in soul
    assert "Organize the answer by the user's question rather than by source order" in soul


def test_government_project_runtime_prompt_requires_synthesis():
    from deerflow.agents.lead_agent.prompt import apply_prompt_template

    prompt = apply_prompt_template(agent_name="government-project-declaration", output_language="zh-CN")

    assert "Never concatenate search hits, file chunks, or tool summaries" in prompt
    assert "build an internal synthesis" in prompt
    assert "rather than from source order" in prompt
    assert "Output language: zh-CN" in prompt
    assert "Default to Simplified Chinese" in prompt
    assert "Markdown contract" in prompt
    assert "Close all fenced code blocks" in prompt
    assert "Translate subagent section labels" in prompt
    assert "heterogeneous capability experts" in prompt
    assert "not fictional roles" in prompt
    assert "because several agents repeat it" in prompt
    assert "evidence-to-claim matrix" in prompt
    assert "Runtime tool preferences:\n- Knowledge-base retrieval: enabled\n- Plan/Todo workflow: enabled\n- Web search: enabled" in prompt
    assert "Runtime capability preferences:" in prompt
    assert "- Web search: enabled" in prompt


def test_government_project_runtime_prompt_parallelizes_complex_research_tasks():
    from deerflow.agents.lead_agent.prompt import apply_prompt_template

    prompt = apply_prompt_template(
        agent_name="government-project-declaration",
        subagent_enabled=True,
        max_concurrent_subagents=3,
    )

    assert "Complex declaration research tasks are decomposable by default" in prompt
    assert "research-status reviews, literature reviews" in prompt
    assert "decompose -> delegate" in prompt
    assert "Launch one focused initial batch" in prompt
    assert "prefer 2-3 when the evidence domains genuinely differ" in prompt
    assert "Do not launch ordinary second or later batches" in prompt
    assert "parallel `task` calls before any" in prompt
    assert "lead-agent `web_search`, `web_fetch`, or `web_extract` call" in prompt
    assert "mandatory for government-project research-status" in prompt
    assert "partially succeeds" in prompt
    assert "at most one additional gap-filling `task`" in prompt
    assert "Prefer `literature-researcher`" in prompt
    assert "standards-patent-researcher" in prompt
    assert "at most 2 `web_search` calls" in prompt
    assert "Avoid repeated lead-agent" in prompt


def test_government_subagent_prompt_uses_enforced_tool_limits():
    from types import SimpleNamespace

    from deerflow.agents.lead_agent.prompt import _build_government_subagent_section
    from deerflow.config.subagents_config import SubagentsAppConfig

    app_config = SimpleNamespace(
        subagents=SubagentsAppConfig(tool_call_limits={"web_search": 1, "web_fetch": 4})
    )

    prompt = _build_government_subagent_section(3, app_config=app_config)

    assert "at most 1 `web_search`, 4 `web_fetch` calls per delegated task" in prompt
    assert "`web_extract`" not in prompt
