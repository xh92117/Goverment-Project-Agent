"""Runtime facade for Agent Base integrations."""
# ruff: noqa: F822

__all__ = [
    "END_SENTINEL",
    "HEARTBEAT_SENTINEL",
    "ConflictError",
    "DisconnectMode",
    "MemoryStreamBridge",
    "RunContext",
    "RunManager",
    "RunRecord",
    "RunStatus",
    "StreamBridge",
    "StreamEvent",
    "ThreadState",
    "UnsupportedStrategyError",
    "checkpointer_context",
    "get_checkpointer",
    "get_store",
    "make_checkpointer",
    "make_store",
    "make_stream_bridge",
    "reset_checkpointer",
    "reset_store",
    "run_agent",
    "serialize",
    "serialize_channel_values",
    "serialize_lc_object",
    "serialize_messages_tuple",
    "store_context",
]


def __getattr__(name: str):
    from importlib import import_module

    if name == "ThreadState":
        return getattr(import_module("deerflow.agents.thread_state"), name)
    if name in __all__:
        return getattr(import_module("deerflow.runtime"), name)
    raise AttributeError(name)
