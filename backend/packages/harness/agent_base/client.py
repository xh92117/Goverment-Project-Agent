"""Neutral embedded-client entrypoint for Agent Base.

The implementation still lives in ``deerflow.client`` for compatibility. This
module gives downstream applications a brand-neutral import path without
forcing a breaking package rename.
"""
# ruff: noqa: F822

from typing import Any

__all__ = ["AgentBaseClient", "StreamEvent"]


class AgentBaseClient:
    """Lazy construction alias for the embedded compatibility client.

    Instantiating this class returns a ``deerflow.client.DeerFlowClient``
    instance. Importing the alias itself stays lightweight so projects can
    depend on ``agent_base`` modules even when optional embedded-client
    dependencies are not installed yet.
    """

    def __new__(cls, *args: Any, **kwargs: Any):
        from deerflow.client import DeerFlowClient

        return DeerFlowClient(*args, **kwargs)


def __getattr__(name: str):
    if name == "StreamEvent":
        from deerflow.client import StreamEvent

        return StreamEvent
    raise AttributeError(name)
