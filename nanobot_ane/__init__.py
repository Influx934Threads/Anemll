"""
Nanobot ANE Integration - Continuous context compression using Apple Neural Engine

This module provides:
- ANEService: Core compression service running on Apple Neural Engine
- ANEInference: Direct ANE model inference

Integration with nanobot is done via patches/ directory which modifies
nanobot's memory.py to call ANE during compaction (see INTEGRATION.md).
"""

from .service import ANEService
from .ane_inference import ANEInference

__all__ = [
    "ANEService",
    "ANEInference",
]
