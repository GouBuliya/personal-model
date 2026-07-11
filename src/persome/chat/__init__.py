"""Chat subsystem — interactive chat, agent loop, history, skills and tools.

Re-exports the public entry points of :mod:`persome.chat.handler`
(formerly the top-level ``persome.chat`` module).
"""

from .approvals import ToolApprovalContext, ToolApprovalRequest
from .handler import TurnResult, run_chat, run_chat_sync

__all__ = [
    "ToolApprovalContext",
    "ToolApprovalRequest",
    "TurnResult",
    "run_chat",
    "run_chat_sync",
]
