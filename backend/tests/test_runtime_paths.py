"""Runtime path policy tests for standalone harness usage."""

from pathlib import Path

import pytest
import yaml

from deerflow import government_project_workspace as gp_workspace
from deerflow.config import app_config as app_config_module
from deerflow.config import extensions_config as extensions_config_module
from deerflow.config import skills_config as skills_config_module
from deerflow.config.app_config import AppConfig
from deerflow.config.extensions_config import ExtensionsConfig
from deerflow.config.paths import Paths
from deerflow.config.runtime_paths import project_root
from deerflow.config.skills_config import SkillsConfig
from deerflow.skills.storage import get_or_new_skill_storage


def _clear_path_env(monkeypatch):
    for name in (
        "AGENT_BASE_CONFIG_PATH",
        "AGENT_BASE_DB_PATH",
        "AGENT_BASE_EXTENSIONS_CONFIG_PATH",
        "AGENT_BASE_HOME",
        "AGENT_BASE_HOST_BASE_DIR",
        "AGENT_BASE_HOST_SKILLS_PATH",
        "AGENT_BASE_PROJECT_ROOT",
        "AGENT_BASE_REPO_ROOT",
        "AGENT_BASE_SKILLS_PATH",
        "AGENT_BASE_DOCKER_SOCKET",
        "DEER_FLOW_CONFIG_PATH",
        "DEER_FLOW_DB_PATH",
        "DEER_FLOW_EXTENSIONS_CONFIG_PATH",
        "DEER_FLOW_HOME",
        "DEER_FLOW_HOST_BASE_DIR",
        "DEER_FLOW_HOST_SKILLS_PATH",
        "DEER_FLOW_PROJECT_ROOT",
        "DEER_FLOW_REPO_ROOT",
        "DEER_FLOW_SKILLS_PATH",
        "DEER_FLOW_DOCKER_SOCKET",
        "GOVERNMENT_PROJECT_WORKSPACE_ROOT",
        "AGENT_BASE_KNOWLEDGE_ROOT",
        "GOVERNMENT_PROJECT_DRAFTS_ROOT",
        "GOVERNMENT_PROJECT_LOG_ROOT",
    ):
        monkeypatch.delenv(name, raising=False)


def test_default_runtime_paths_resolve_from_current_project(tmp_path: Path, monkeypatch):
    _clear_path_env(monkeypatch)
    monkeypatch.chdir(tmp_path)

    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump({"sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"}}),
        encoding="utf-8",
    )
    (tmp_path / "extensions_config.json").write_text('{"mcpServers": {}, "skills": {}}', encoding="utf-8")
    (tmp_path / "skills").mkdir()

    assert AppConfig.resolve_config_path() == tmp_path / "config.yaml"
    assert ExtensionsConfig.resolve_config_path() == tmp_path / "extensions_config.json"
    assert Paths().base_dir == tmp_path / ".agent-base"
    assert SkillsConfig().get_skills_path() == tmp_path / "skills"
    assert get_or_new_skill_storage(skills_path=SkillsConfig().get_skills_path()).get_skills_root_path() == tmp_path / "skills"


def test_deer_flow_project_root_overrides_current_directory(tmp_path: Path, monkeypatch):
    _clear_path_env(monkeypatch)
    project_root = tmp_path / "project"
    other_cwd = tmp_path / "other"
    project_root.mkdir()
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)
    monkeypatch.setenv("DEER_FLOW_PROJECT_ROOT", str(project_root))

    (project_root / "config.yaml").write_text(
        yaml.safe_dump({"sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"}}),
        encoding="utf-8",
    )
    (project_root / "mcp_config.json").write_text('{"mcpServers": {}, "skills": {}}', encoding="utf-8")

    assert AppConfig.resolve_config_path() == project_root / "config.yaml"
    assert ExtensionsConfig.resolve_config_path() == project_root / "mcp_config.json"
    assert Paths().base_dir == project_root / ".agent-base"
    assert SkillsConfig(path="custom-skills").get_skills_path() == project_root / "custom-skills"


def test_agent_base_config_path_overrides_legacy_config_path(tmp_path: Path, monkeypatch):
    _clear_path_env(monkeypatch)
    agent_config = tmp_path / "agent-config.yaml"
    legacy_config = tmp_path / "legacy-config.yaml"
    agent_config.write_text(
        yaml.safe_dump({"sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"}}),
        encoding="utf-8",
    )
    legacy_config.write_text("", encoding="utf-8")
    monkeypatch.setenv("AGENT_BASE_CONFIG_PATH", str(agent_config))
    monkeypatch.setenv("DEER_FLOW_CONFIG_PATH", str(legacy_config))

    assert AppConfig.resolve_config_path() == agent_config


def test_legacy_config_path_still_supported(tmp_path: Path, monkeypatch):
    _clear_path_env(monkeypatch)
    legacy_config = tmp_path / "legacy-config.yaml"
    legacy_config.write_text(
        yaml.safe_dump({"sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("DEER_FLOW_CONFIG_PATH", str(legacy_config))

    assert AppConfig.resolve_config_path() == legacy_config


def test_agent_base_extensions_config_path_overrides_legacy_path(tmp_path: Path, monkeypatch):
    _clear_path_env(monkeypatch)
    agent_extensions = tmp_path / "agent-extensions.json"
    legacy_extensions = tmp_path / "legacy-extensions.json"
    agent_extensions.write_text('{"mcpServers": {}, "skills": {}}', encoding="utf-8")
    legacy_extensions.write_text('{"mcpServers": {"legacy": {}}, "skills": {}}', encoding="utf-8")
    monkeypatch.setenv("AGENT_BASE_EXTENSIONS_CONFIG_PATH", str(agent_extensions))
    monkeypatch.setenv("DEER_FLOW_EXTENSIONS_CONFIG_PATH", str(legacy_extensions))

    assert ExtensionsConfig.resolve_config_path() == agent_extensions


def test_legacy_extensions_config_path_still_supported(tmp_path: Path, monkeypatch):
    _clear_path_env(monkeypatch)
    legacy_extensions = tmp_path / "legacy-extensions.json"
    legacy_extensions.write_text('{"mcpServers": {}, "skills": {}}', encoding="utf-8")
    monkeypatch.setenv("DEER_FLOW_EXTENSIONS_CONFIG_PATH", str(legacy_extensions))

    assert ExtensionsConfig.resolve_config_path() == legacy_extensions


def test_agent_base_home_overrides_legacy_home(tmp_path: Path, monkeypatch):
    _clear_path_env(monkeypatch)
    agent_base_home = tmp_path / "agent-base-home"
    legacy_home = tmp_path / "legacy-home"
    monkeypatch.setenv("AGENT_BASE_HOME", str(agent_base_home))
    monkeypatch.setenv("DEER_FLOW_HOME", str(legacy_home))

    assert Paths().base_dir == agent_base_home


def test_runtime_home_falls_back_to_existing_legacy_state_dir(tmp_path: Path, monkeypatch):
    _clear_path_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    legacy_home = tmp_path / ".deer-flow"
    legacy_home.mkdir()

    assert Paths().base_dir == legacy_home


def test_runtime_home_prefers_agent_base_state_dir_when_both_exist(tmp_path: Path, monkeypatch):
    _clear_path_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    legacy_home = tmp_path / ".deer-flow"
    agent_base_home = tmp_path / ".agent-base"
    legacy_home.mkdir()
    agent_base_home.mkdir()

    assert Paths().base_dir == agent_base_home


def test_deer_flow_skills_path_overrides_project_default(tmp_path: Path, monkeypatch):
    _clear_path_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEER_FLOW_SKILLS_PATH", "team-skills")

    assert SkillsConfig().get_skills_path() == tmp_path / "team-skills"
    assert get_or_new_skill_storage(skills_path=SkillsConfig().get_skills_path()).get_skills_root_path() == tmp_path / "team-skills"


def test_agent_base_skills_path_overrides_legacy_skills_path(tmp_path: Path, monkeypatch):
    _clear_path_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    agent_skills = tmp_path / "agent-skills"
    legacy_skills = tmp_path / "legacy-skills"
    monkeypatch.setenv("AGENT_BASE_SKILLS_PATH", str(agent_skills))
    monkeypatch.setenv("DEER_FLOW_SKILLS_PATH", str(legacy_skills))

    assert SkillsConfig().get_skills_path() == agent_skills


def test_deer_flow_project_root_must_exist(tmp_path: Path, monkeypatch):
    _clear_path_env(monkeypatch)
    missing_root = tmp_path / "missing"
    monkeypatch.setenv("DEER_FLOW_PROJECT_ROOT", str(missing_root))

    with pytest.raises(ValueError, match="does not exist"):
        project_root()


def test_deer_flow_project_root_must_be_directory(tmp_path: Path, monkeypatch):
    _clear_path_env(monkeypatch)
    project_root_file = tmp_path / "project-root"
    project_root_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("DEER_FLOW_PROJECT_ROOT", str(project_root_file))

    with pytest.raises(ValueError, match="not a directory"):
        project_root()


def test_app_config_falls_back_to_legacy_when_project_root_lacks_config(tmp_path: Path, monkeypatch):
    """When DEER_FLOW_PROJECT_ROOT is unset and cwd has no config.yaml, the
    legacy backend/repo-root candidates must be used for monorepo compatibility."""
    _clear_path_env(monkeypatch)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)

    legacy_backend = tmp_path / "legacy-backend"
    legacy_repo = tmp_path / "legacy-repo"
    legacy_backend.mkdir()
    legacy_repo.mkdir()
    legacy_backend_config = legacy_backend / "config.yaml"
    legacy_backend_config.write_text(
        yaml.safe_dump({"sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"}}),
        encoding="utf-8",
    )
    repo_root_config = legacy_repo / "config.yaml"
    repo_root_config.write_text("", encoding="utf-8")

    monkeypatch.setattr(
        app_config_module,
        "_legacy_config_candidates",
        lambda: (legacy_backend_config, repo_root_config),
    )

    assert AppConfig.resolve_config_path() == legacy_backend_config


def test_skills_config_falls_back_to_legacy_when_project_root_lacks_skills(tmp_path: Path, monkeypatch):
    """When DEER_FLOW_PROJECT_ROOT is unset and cwd has no `skills/`, the legacy
    repo-root candidate must be used so monorepo runs (cwd=backend/) keep finding
    `<repo>/skills` instead of `<repo>/backend/skills` (regression test for #2694)."""
    _clear_path_env(monkeypatch)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)

    legacy_skills = tmp_path / "legacy-repo" / "skills"
    legacy_skills.mkdir(parents=True)

    monkeypatch.setattr(
        skills_config_module,
        "_legacy_skills_candidates",
        lambda: (legacy_skills,),
    )

    assert SkillsConfig().get_skills_path() == legacy_skills


def test_skills_config_returns_project_default_when_neither_exists(tmp_path: Path, monkeypatch):
    """When nothing exists, fall back to the project-root default path so callers
    surface a stable empty location instead of silently picking a stale legacy dir."""
    _clear_path_env(monkeypatch)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)

    monkeypatch.setattr(skills_config_module, "_legacy_skills_candidates", lambda: ())

    assert SkillsConfig().get_skills_path() == cwd / "skills"


def test_extensions_config_falls_back_to_legacy_when_project_root_lacks_file(tmp_path: Path, monkeypatch):
    """ExtensionsConfig should hit the legacy backend/repo-root locations when
    the caller project root has no extensions_config.json/mcp_config.json."""
    _clear_path_env(monkeypatch)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)

    fake_backend = tmp_path / "fake-backend"
    fake_repo = tmp_path / "fake-repo"
    fake_backend.mkdir()
    fake_repo.mkdir()
    legacy_extensions = fake_backend / "extensions_config.json"
    legacy_extensions.write_text('{"mcpServers": {}, "skills": {}}', encoding="utf-8")

    fake_paths_module_file = fake_backend / "packages" / "harness" / "deerflow" / "config" / "extensions_config.py"
    fake_paths_module_file.parent.mkdir(parents=True)
    fake_paths_module_file.write_text("", encoding="utf-8")

    monkeypatch.setattr(extensions_config_module, "__file__", str(fake_paths_module_file))

    assert ExtensionsConfig.resolve_config_path() == legacy_extensions


def test_government_project_runtime_defaults_to_external_c_workspace(monkeypatch):
    _clear_path_env(monkeypatch)

    workspace = gp_workspace.government_project_workspace_root()

    assert workspace == Path(r"C:\Users\Administrator\GP Agent\workspace")
    assert gp_workspace.government_project_knowledge_root() == workspace / "knowledge_base"
    assert gp_workspace.government_project_drafts_root() == workspace / "proposal_drafts"
    assert gp_workspace.government_project_logs_root() == workspace / "logs"


@pytest.mark.parametrize(
    ("env_name", "resolver"),
    [
        ("GOVERNMENT_PROJECT_WORKSPACE_ROOT", gp_workspace.government_project_workspace_root),
        ("AGENT_BASE_KNOWLEDGE_ROOT", gp_workspace.government_project_knowledge_root),
        ("GOVERNMENT_PROJECT_DRAFTS_ROOT", gp_workspace.government_project_drafts_root),
        ("GOVERNMENT_PROJECT_LOG_ROOT", gp_workspace.government_project_logs_root),
    ],
)
def test_government_project_runtime_paths_reject_source_tree(env_name, resolver, monkeypatch):
    _clear_path_env(monkeypatch)
    monkeypatch.setenv(env_name, str(gp_workspace.repo_root() / "workspace"))

    with pytest.raises(ValueError, match="outside the source-code tree"):
        resolver()


def test_knowledge_storage_reuses_government_path_policy(monkeypatch):
    _clear_path_env(monkeypatch)
    monkeypatch.setenv("AGENT_BASE_KNOWLEDGE_ROOT", str(gp_workspace.repo_root() / "workspace" / "knowledge_base"))

    from deerflow.knowledge import storage as knowledge_storage

    with pytest.raises(ValueError, match="outside the source-code tree"):
        knowledge_storage._knowledge_root_path()
