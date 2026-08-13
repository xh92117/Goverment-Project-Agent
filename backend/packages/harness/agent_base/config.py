"""Configuration facade for Agent Base integrations.

Function exports are wrappers so importing ``agent_base.config`` stays
lightweight. The underlying compatibility modules load only when a caller uses
the function or requests a config model.
"""
# ruff: noqa: F822

from typing import Any

__all__ = [
    "ExtensionsConfig",
    "LoopDetectionConfig",
    "MemoryConfig",
    "Paths",
    "SkillEvolutionConfig",
    "SkillsConfig",
    "get_app_config",
    "get_enabled_tracing_providers",
    "get_explicitly_enabled_tracing_providers",
    "get_extensions_config",
    "get_memory_config",
    "get_paths",
    "get_tracing_config",
    "is_tracing_enabled",
    "validate_enabled_tracing_providers",
]

_MODEL_MODULES = {
    "ExtensionsConfig": "deerflow.config.extensions_config",
    "LoopDetectionConfig": "deerflow.config.loop_detection_config",
    "MemoryConfig": "deerflow.config.memory_config",
    "Paths": "deerflow.config.paths",
    "SkillEvolutionConfig": "deerflow.config.skill_evolution_config",
    "SkillsConfig": "deerflow.config.skills_config",
}


def get_app_config(*args: Any, **kwargs: Any):
    from deerflow.config import get_app_config as _get_app_config

    return _get_app_config(*args, **kwargs)


def get_extensions_config(*args: Any, **kwargs: Any):
    from deerflow.config import get_extensions_config as _get_extensions_config

    return _get_extensions_config(*args, **kwargs)


def get_memory_config(*args: Any, **kwargs: Any):
    from deerflow.config import get_memory_config as _get_memory_config

    return _get_memory_config(*args, **kwargs)


def get_paths(*args: Any, **kwargs: Any):
    from deerflow.config.paths import get_paths as _get_paths

    return _get_paths(*args, **kwargs)


def get_tracing_config(*args: Any, **kwargs: Any):
    from deerflow.config import get_tracing_config as _get_tracing_config

    return _get_tracing_config(*args, **kwargs)


def get_explicitly_enabled_tracing_providers(*args: Any, **kwargs: Any):
    from deerflow.config import get_explicitly_enabled_tracing_providers as _fn

    return _fn(*args, **kwargs)


def get_enabled_tracing_providers(*args: Any, **kwargs: Any):
    from deerflow.config import get_enabled_tracing_providers as _fn

    return _fn(*args, **kwargs)


def is_tracing_enabled(*args: Any, **kwargs: Any):
    from deerflow.config import is_tracing_enabled as _is_tracing_enabled

    return _is_tracing_enabled(*args, **kwargs)


def validate_enabled_tracing_providers(*args: Any, **kwargs: Any):
    from deerflow.config import validate_enabled_tracing_providers as _fn

    return _fn(*args, **kwargs)


def __getattr__(name: str):
    module_name = _MODEL_MODULES.get(name)
    if module_name is None:
        raise AttributeError(name)

    from importlib import import_module

    return getattr(import_module(module_name), name)
