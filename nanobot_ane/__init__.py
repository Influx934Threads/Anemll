"""
Nanobot ANE Integration - Continuous context compression using Apple Neural Engine

This module provides:
- ANEService: Core compression service running on Apple Neural Engine
- ANEHook: Nanobot AgentHook for automatic turn compression
- ANEInference: Direct ANE model inference
- ane_context_provider: RuntimeContextProvider for injecting compressed context
"""

from .service import ANEService
from .hook import ANEHook
from .context_provider import ane_context_provider, create_ane_context_provider
from .ane_inference import ANEInference

__all__ = [
    "ANEService",
    "ANEHook",
    "ANEInference",
    "ane_context_provider",
    "create_ane_context_provider",
]
