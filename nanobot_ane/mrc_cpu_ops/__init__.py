"""
MRC CPU Operations

CPU-based operations for Memory Rolling Compression (MRC).
Foundation layer - always available, no NPU required.

Components:
- mrc_mechanical_merger: Entity-aware deduplication (100% TRUE recall, 316x faster)
"""
from .mrc_mechanical_merger import MechanicalMerger, EntityDeduplicator

__all__ = ['MechanicalMerger', 'EntityDeduplicator']
