"""IM channel integration for Agent Base.

Provides a pluggable channel system that connects external messaging platforms
(DingTalk, Feishu/Lark, WeChat, WeCom) to the Agent Base runtime via the ChannelManager,
which uses ``langgraph-sdk`` to communicate with Gateway's LangGraph-compatible API.
"""

from app.channels.base import Channel
from app.channels.message_bus import InboundMessage, MessageBus, OutboundMessage

__all__ = [
    "Channel",
    "InboundMessage",
    "MessageBus",
    "OutboundMessage",
]
