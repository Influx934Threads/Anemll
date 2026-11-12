# Memory Rolling Compression (MRC) Refactoring Plan

**Date**: 2026-11-11
**Purpose**: Rename from ANE-specific to NPU-agnostic architecture
**Goal**: Make rolling compression portable across NPU platforms
**New Name**: Memory Rolling Compression (MRC)
**Acronym**: MRC
**Module**: `memory_rolling_compression` (was `nanobot_ane`)

---

## Executive Summary

**Key Naming Decision**: "Memory Rolling Compression" (MRC)

This refactoring renames the project from `nanobot_ane` (ANE-specific) to `memory_rolling_compression` (platform-agnostic) with the **MRC** acronym and `mrc_` file prefix throughout.

**Why MRC?**
- **Memory**: Makes it clear this compresses conversation memory/context
- **Rolling**: Describes the continuous, incremental compression mechanism
- **Compression**: The core function
- **Acronym**: MRC is clean, professional, and memorable

The core innovation is **Rolling Compression** - continuous turn-by-turn background compression with hybrid NPU+CPU techniques. ANE is just ONE NPU backend. This refactoring:

1. Clarifies what's generic rolling compression vs NPU-specific
2. Makes the system portable to other NPU platforms
3. Better reflects the actual hybrid architecture (NPU for LLM inference + CPU for mechanical merge)
4. Improves nanobot integration naming

---

## Current Architecture Analysis

### What Uses NPU (LLM Inference)
```
ane_inference.py
├─ Fact extraction (Budget 100 prompt) ~5s per turn
└─ Consolidation (every 5 turns) ~10s
```

**NPU Dependency**: CoreML model loading, ANE-specific inference

### What Uses CPU (Zero-LLM, Fast)
```
mechanical_merger.py
├─ Fuzzy deduplication (threshold 0.85)
├─ Fact merging
└─ Text consolidation
```

**No NPU needed**: Pure algorithmic, milliseconds

### What's Generic (Rolling Compression Mechanism)
```
service.py + daemon.py
├─ Background polling (every 10s)
├─ Turn detection and queuing
├─ Session management
├─ Checkpoint serving
├─ HTTP API
└─ State persistence
```

**Platform agnostic**: Works with any NPU backend

---

## Key Architectural Insight

**The system is ALREADY hybrid NPU+CPU:**

```
┌────────────────────────────────────────────────────────────────┐
│                   ROLLING COMPRESSION SERVICE                   │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────┐        ┌──────────────────────────────┐ │
│  │  NPU Backend     │        │  CPU Operations              │ │
│  │  (Pluggable)     │        │  (Always Available)          │ │
│  ├──────────────────┤        ├──────────────────────────────┤ │
│  │ - Fact Extract   │        │ - Mechanical Merge           │ │
│  │ - Consolidation  │        │ - Fuzzy Deduplication        │ │
│  │                  │        │ - Session Management         │ │
│  │ Platform:        │        │ - Polling                    │ │
│  │ • ANE (Apple)    │        │ - HTTP Serving               │ │
│  │ • AMD NPU        │        │ - State Persistence          │ │
│  │ • Intel NPU      │        │                              │ │
│  │ • Qualcomm NPU   │        │ Zero-LLM, Milliseconds       │ │
│  │                  │        │                              │ │
│  │ ~5-10s per turn  │        └──────────────────────────────┘ │
│  └──────────────────┘                                          │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

**Current problem**: Everything named "ANE" even though most of it isn't ANE-specific.

---

## CPU Operations: EntityDeduplicator (Foundation Layer)

**Update (2026-11-12)**: Testing confirms **EntityDeduplicator** is superior to string-based deduplication.

### Performance Summary

| Metric | String-based | Entity-based | Improvement |
|--------|--------------|--------------|-------------|
| **TRUE RECALL** | 100% (9/9 unique) | 100% (9/9 unique) | Equal (perfect) |
| **Deduplication Quality** | 12 facts (+3 extra) | 10 facts (+1 extra) | **33% better** |
| **Speed (avg)** | 379ms | 1.2ms | **316x faster** |
| **Semantic Accuracy** | Over-preserves duplicates | Correctly merges rephrased | **Better** |

### How EntityDeduplicator Works

```python
class EntityDeduplicator:
    """
    Extract entities (numbers, capitalized words, units)
    Compare using Jaccard similarity on entity sets (50% threshold)
    """

    def deduplicate(self, facts):
        for each fact:
            1. Extract entities: re.findall(r'\d+', content)
            2. Compare entity set to all seen sets
            3. Jaccard = overlap / union
            4. If Jaccard > 50%, mark as duplicate
            5. Else keep as unique

# Example:
fact1 = "timeout: 30s" → entities: {'30'}
fact2 = "timeout: 60s" → entities: {'60'}
Jaccard = 0/2 = 0% → Keep both ✓ (different values)

fact3 = "timeout set to 30s" → entities: {'30'}
Jaccard with fact1 = 1/1 = 100% → Merge ✓ (same value)
```

### Why Entity-Based is Superior

1. **100% TRUE recall**: All unique semantic information preserved
2. **Better deduplication**: Correctly identifies rephrased duplicates with same entities
3. **Semantic accuracy**: "timeout: 30s" ≠ "timeout: 60s" (different values preserved)
4. **Production performance**: 316x faster (1.2ms vs 379ms average)
5. **Scales to production**: <5ms for 1000 facts vs 5.5s for string-based

### Test Evidence

- **Ground truth validated**: 9 unique semantic facts, both approaches preserve all 9
- **String-based output**: 12 facts (over-preserves 3 duplicates)
- **Entity-based output**: 10 facts (over-preserves only 1 duplicate)
- **Tested on**: 14-200 facts across 5 datasets (ARM C, nanobot history, synthetic)

**Decision**: Use EntityDeduplicator as default for `mrc_mechanical_merger.py`

---

## Renaming Plan: Memory Rolling Compression (MRC)

### Naming Convention

**Full Name**: Memory Rolling Compression
**Acronym**: MRC
**File Prefix**: `mrc_` for all core files
**Module Name**: `memory_rolling_compression`

### Phase 1: Directory Restructure (Preserve Git History)

```bash
# Current
nanobot_ane/
├── ane_daemon.py          # Generic rolling compression daemon
├── ane_inference.py       # ANE-specific (CoreML)
├── service.py             # Generic rolling compression service
├── ane_client.py          # Generic HTTP client
└── arms/
    └── arm_c/
        └── mechanical_merger.py  # CPU-based (already good)

# Proposed: Memory Rolling Compression (MRC)
memory_rolling_compression/       # Renamed from nanobot_ane
├── mrc_daemon.py                 # Generic daemon (was ane_daemon.py)
├── mrc_service.py                # Generic service (was service.py)
├── mrc_client.py                 # Generic client (was ane_client.py)
├── mrc_backends/                 # NEW: Pluggable NPU abstraction
│   ├── __init__.py
│   ├── mrc_base.py               # Abstract NPU interface
│   ├── mrc_ane.py                # Apple Neural Engine (was ane_inference.py)
│   ├── mrc_amd_npu.py            # Future: AMD NPU via FastFlowLM
│   ├── mrc_intel_npu.py          # Future: Intel NPU via OpenVINO
│   └── mrc_gpu_fallback.py       # Future: GPU via llama.cpp
└── mrc_cpu_ops/                  # CPU-based operations
    └── mrc_mechanical_merger.py  # Moved from arms/arm_c/mechanical_merger.py
```

**Git-safe operations:**
```bash
# Preserve history
git mv nanobot_ane memory_rolling_compression
cd memory_rolling_compression

# Rename core files with mrc_ prefix
git mv ane_daemon.py mrc_daemon.py
git mv service.py mrc_service.py
git mv nanobot_patches/ane_client.py mrc_client.py

# Extract NPU backend
mkdir -p mrc_backends
git mv ane_inference.py mrc_backends/mrc_ane.py

# Move CPU operations
mkdir -p mrc_cpu_ops
git mv arms/arm_c/mechanical_merger.py mrc_cpu_ops/mrc_mechanical_merger.py
```

### Phase 2: Code Renaming

**File-by-File Changes:**

| File | Old Class/Function | New Name (MRC) | Rationale |
|------|-------------------|----------------|-----------|
| `mrc_service.py` | `ANEService` | `MRCService` | Memory Rolling Compression service |
| `mrc_daemon.py` | `ANEDaemon` | `MRCDaemon` | MRC daemon |
| `mrc_client.py` | `ANEClient` | `MRCClient` | MRC HTTP client |
| `mrc_backends/mrc_base.py` | N/A | `MRCBackend` (abstract) | Backend interface |
| `mrc_backends/mrc_ane.py` | `ANEInference` | `MRCBackendANE` | Apple Neural Engine backend |

**String Replacements (274 occurrences):**

```bash
# User-facing strings
"ANE compression" → "Memory rolling compression" or "MRC"
"ANE daemon" → "MRC daemon"
"Apple Neural Engine" → "MRC backend (Apple Neural Engine)"

# Internal variable names
ane_service → mrc_service
ane_daemon → mrc_daemon
ane_client → mrc_client
```

### Phase 3: Nanobot Integration Rename

**nanobot_patches/ → nanobot_integration/**

```python
# OLD (nanobot_patches/ane_client.py)
from nanobot.agent.ane_client import get_ane_client

# NEW (nanobot_integration/mrc_client.py)
from nanobot.agent.mrc_client import get_mrc_client
```

**Patch file rename:**
```
memory_ane_integration.patch → memory_mrc_integration.patch
```

**Updated patch content:**
```python
# Import section
-from nanobot.agent.ane_client import get_ane_client, ANEClient
+from nanobot.agent.mrc_client import get_mrc_client, MRCClient

# Availability check
-_ANE_AVAILABLE = True
+_MRC_AVAILABLE = True

# Usage
-        # ── TRY ANE COMPRESSION FIRST ──
-        # ANE runs on Apple Neural Engine - much faster and doesn't use API credits
+        # ── TRY MRC FIRST ──
+        # Memory Rolling Compression uses NPU backend (ANE on Apple)
+        # Much faster and doesn't use API credits
```

---

## NPU Backend Abstraction

### Abstract Interface

```python
# memory_rolling_compression/mrc_backends/mrc_base.py

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Optional

class MRCBackend(ABC):
    """Abstract interface for NPU inference backends.

    Implementations provide LLM inference for:
    - Fact extraction (Budget 100 prompt)
    - Optional consolidation (may use CPU mechanical merge instead)
    """

    @abstractmethod
    def __init__(self, model_path: Path, **kwargs):
        """Initialize backend with model path and config."""
        pass

    @abstractmethod
    async def load_model(self) -> None:
        """Load model into NPU memory."""
        pass

    @abstractmethod
    async def infer(self, prompt: str, config: Dict[str, Any]) -> str:
        """Run inference on NPU.

        Args:
            prompt: Input prompt
            config: Generation config (max_tokens, temperature, etc.)

        Returns:
            Generated text
        """
        pass

    @abstractmethod
    async def unload_model(self) -> None:
        """Unload model from NPU memory."""
        pass

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Backend identifier (e.g., 'ane', 'amd-npu', 'intel-npu')."""
        pass

    @property
    @abstractmethod
    def device_info(self) -> Dict[str, Any]:
        """Device information (memory, throughput estimates, etc.)."""
        pass
```

### ANE Implementation

```python
# memory_rolling_compression/mrc_backends/mrc_ane.py

from pathlib import Path
from typing import Dict, Any
import coremltools as ct

from .mrc_base import MRCBackend

class MRCBackendANE(MRCBackend):
    """Apple Neural Engine backend via CoreML.

    Optimized for M-series chips with ANE acceleration.
    """

    def __init__(self, model_path: Path, **kwargs):
        self.model_path = model_path
        self.model = None
        self._device_info = self._detect_device()

    async def load_model(self) -> None:
        # Existing ANEInference logic
        self.model = ct.models.MLModel(
            str(self.model_path),
            compute_units=ct.ComputeUnit.CPU_AND_NE
        )

    async def infer(self, prompt: str, config: Dict[str, Any]) -> str:
        # Existing inference logic
        pass

    @property
    def backend_name(self) -> str:
        return "ane"

    @property
    def device_info(self) -> Dict[str, Any]:
        return self._device_info

    def _detect_device(self) -> Dict[str, Any]:
        # Detect M1/M2/M3, memory, etc.
        import platform
        return {
            "platform": platform.machine(),
            "backend": "Apple Neural Engine (CoreML)",
        }
```

### Backend Factory

```python
# memory_rolling_compression/mrc_backends/__init__.py

from pathlib import Path
from typing import Optional
import platform

from .mrc_base import MRCBackend
from .mrc_ane import MRCBackendANE

def auto_detect_backend() -> str:
    """Detect best available NPU backend for current platform."""
    system = platform.system()
    machine = platform.machine()

    if system == "Darwin" and machine in ("arm64", "x86_64"):
        # macOS with potential ANE support
        return "ane"

    # Future: detect AMD NPU, Intel NPU, etc.
    # elif has_amd_npu():
    #     return "amd-npu"

    return None  # No NPU available


def create_backend(
    backend_type: Optional[str] = None,
    model_path: Optional[Path] = None,
    **kwargs
) -> MRCBackend:
    """Create MRC backend instance.

    Args:
        backend_type: Backend name ("ane", "amd-npu", etc.) or None for auto-detect
        model_path: Path to model files
        **kwargs: Backend-specific configuration

    Returns:
        MRCBackend instance

    Raises:
        ValueError: If backend not available
    """
    if backend_type is None:
        backend_type = auto_detect_backend()

    if backend_type is None:
        raise ValueError("No NPU backend available on this platform")

    if backend_type == "ane":
        return MRCBackendANE(model_path, **kwargs)
    # elif backend_type == "amd-npu":
    #     return MRCBackendAMDNPU(model_path, **kwargs)

    raise ValueError(f"Unknown backend: {backend_type}")
```

### Service Integration

```python
# memory_rolling_compression/mrc_service.py

from .mrc_backends import create_backend, MRCBackend

class MRCService:
    def __init__(
        self,
        model_path: Path,
        backend_type: Optional[str] = None,  # Auto-detect if None
        **kwargs
    ):
        self.model_path = model_path

        # Create NPU backend (pluggable)
        self._backend: MRCBackend = create_backend(
            backend_type=backend_type,
            model_path=model_path,
        )

        # CPU operations (always available)
        from .mrc_cpu_ops.mrc_mechanical_merger import MRCMechanicalMerger
        self.mechanical_merger = MRCMechanicalMerger(threshold=0.85)

    async def start(self):
        await self._backend.load_model()
        logger.info(f"MRC started with {self._backend.backend_name} backend")
```

---

## Configuration Changes

### New Config Format

```yaml
# ~/.nanobot/mrc_config.yaml (was ane_config.yaml)

backend:
  type: auto  # auto, ane, amd-npu, intel-npu, gpu

  # Backend-specific configs
  ane:
    model_path: ~/Build/Anemll/models/qwen3-4b-ctx2048
    compute_units: CPU_AND_NE  # CoreML setting

  # Future backends
  # amd_npu:
  #   model_path: /path/to/onnx/model
  #   device: npu0

compression:
  strategy: budget100
  mechanical_merge_threshold: 0.85
  consolidation_interval: 5  # turns

daemon:
  poll_interval: 10  # seconds
  http_port: 8766
```

### Environment Variable Changes

```bash
# OLD
ANEMLL_ANE_MODEL_PATH=...
ANEMLL_ANE_PORT=...

# NEW (backward compatible with warnings)
MRC_MODEL_PATH=...
MRC_PORT=...
MRC_BACKEND=ane  # or auto
```

---

## CPU Fallback Question: Possible?

**Short answer: Not practical for LLM inference, but YES for the overall system.**

### Why CPU-only LLM inference doesn't make sense:

```
Fact extraction (Budget 100):
- NPU (ANE): ~5s per turn ✅ Background-friendly
- GPU: ~2-3s per turn ✅ Acceptable
- CPU: ~30-60s per turn ❌ Too slow for background

Rolling compression goal: Invisible background work
CPU LLM inference: Blocks too long, defeats purpose
```

### But CPU-only system IS possible:

**Option 1: Pure Mechanical Merge (No LLM)**

```python
# rolling_compression/backends/cpu_only.py

class CPUOnlyBackend(NPUBackend):
    """CPU-only backend with NO LLM inference.

    Uses only mechanical merge for compression.
    Quality: Lower than LLM extraction, but zero latency/cost.
    """

    async def infer(self, prompt: str, config: Dict) -> str:
        # Skip LLM inference entirely
        # Return empty string → triggers mechanical merge only
        return ""
```

**Result:**
- No fact extraction (Budget 100 skipped)
- Pure fuzzy deduplication and merge
- Much lower quality but faster
- Useful for very low-end devices

**Option 2: GPU Fallback**

```python
# rolling_compression/backends/gpu_fallback.py

import llama_cpp

class GPUFallbackBackend(NPUBackend):
    """GPU backend via llama.cpp.

    Not technically "NPU" but fills same role.
    Useful on non-NPU systems with decent GPU.
    """

    def __init__(self, model_path: Path, **kwargs):
        self.llm = llama_cpp.Llama(
            model_path=str(model_path),
            n_gpu_layers=-1,  # Offload all to GPU
            n_ctx=2048,
        )

    async def infer(self, prompt: str, config: Dict) -> str:
        response = self.llm(prompt, **config)
        return response["choices"][0]["text"]
```

**Makes sense for:**
- Linux servers with NVIDIA GPUs
- Windows gaming PCs
- Any system without NPU but with GPU

### Recommendation

**Support 3 backend tiers:**

| Tier | Backend | Quality | Speed | Use Case |
|------|---------|---------|-------|----------|
| **Best** | NPU (ANE/AMD/Intel) | High | ~5s | Apple Silicon, modern laptops |
| **Good** | GPU (llama.cpp) | High | ~3s | Servers, gaming PCs |
| **Basic** | CPU-only (no LLM) | Medium | <1s | Low-end devices, testing |

---

## Migration Path

### Phase 1: Preparation (Week 1)

**No breaking changes, just additions:**

1. Create `backends/` directory structure
2. Add `base.py` abstract interface
3. Move `ane_inference.py` → `backends/ane.py` (but keep old imports working)
4. Add backend factory with auto-detection
5. Update tests to use new backend interface

**Compatibility shim:**
```python
# ane_inference.py (deprecated wrapper)
from rolling_compression.backends.ane import ANEBackend as ANEInference
import warnings

warnings.warn(
    "ane_inference is deprecated, use rolling_compression.backends.ane",
    DeprecationWarning
)
```

### Phase 2: Core Rename (Week 2)

**Breaking changes, documented migration:**

1. Rename directory: `nanobot_ane/` → `rolling_compression/`
2. Rename files: `ane_daemon.py` → `daemon.py`, etc.
3. Update all internal references
4. Update documentation
5. Update nanobot patch

**Migration guide:**
```markdown
# Migration from 0.x to 1.0 (Memory Rolling Compression)

## Quick Fix (5 minutes)
```bash
# Update import paths
sed -i 's/nanobot_ane/memory_rolling_compression/g' your_code.py
sed -i 's/ANEService/MRCService/g' your_code.py
sed -i 's/ANEDaemon/MRCDaemon/g' your_code.py
sed -i 's/ANEClient/MRCClient/g' your_code.py
```

## Config Changes
Rename `~/.nanobot/ane_config.yaml` → `mrc_config.yaml`

## Environment Variables
Update:
- `ANEMLL_ANE_MODEL_PATH` → `MRC_MODEL_PATH`
- `ANEMLL_ANE_PORT` → `MRC_PORT`
```

### Phase 3: Nanobot Integration (Week 3)

1. Update patch file name and content
2. Test with current nanobot version
3. Document as "Rolling Compression Integration"
4. Submit patch to nanobot team as feature (optional)

---

## Documentation Updates

### README.md Changes

**OLD:**
> # nanobot_ane
>
> ANE-powered context compression for nanobot using Apple Neural Engine.

**NEW:**
> # Memory Rolling Compression (MRC) for Nanobot
>
> Continuous turn-by-turn background compression using hybrid NPU+CPU techniques.
>
> **What is MRC?**
> Memory Rolling Compression builds a compressed context cache incrementally in the background,
> serving it instantly when needed. Unlike on-demand compression (tens of seconds),
> MRC pre-computes compression turn-by-turn (~10ms retrieval).
>
> **Supported NPU Backends:**
> - ✅ Apple Neural Engine (M1/M2/M3/M4 Macs)
> - 🚧 AMD NPU (via FastFlowLM) - planned
> - 🚧 Intel NPU (via OpenVINO) - planned
> - 🚧 GPU Fallback (via llama.cpp) - planned
>
> **CPU Operations:**
> - ✅ Mechanical merge (fuzzy deduplication)
> - ✅ Zero-LLM consolidation
>
> **Works with ANY chat provider** - not limited to OpenAI/DeepSeek like provider-native compression.

### Architecture Document

```markdown
# Memory Rolling Compression (MRC) Architecture

## Two-Tier Compression

### Tier 1: NPU-Accelerated LLM Inference
- **Budget 100 fact extraction**: ~5s per turn
- **Periodic consolidation**: Every 5 turns
- **Backend**: Pluggable (ANE, AMD NPU, Intel NPU, GPU)

### Tier 2: CPU-Based Mechanical Operations
- **Fuzzy deduplication**: Milliseconds
- **Fact merging**: Zero-LLM, threshold 0.85
- **Always available**: No NPU required

## Why Hybrid?

NPU for what it's best at: LLM inference (parallelizable, hardware-accelerated)
CPU for what it's best at: Algorithmic operations (deterministic, fast)

Total: Best of both worlds.

## Why "Memory Rolling Compression"?

- **Memory**: Compresses conversation memory/context
- **Rolling**: Continuous, incremental compression (not bulk)
- **Compression**: Reduces tokens while preserving facts
```

---

## Testing Strategy

### Backward Compatibility Tests

```python
# tests/test_backward_compat.py

def test_old_imports_still_work():
    """Deprecated imports should work with warnings."""
    with pytest.warns(DeprecationWarning):
        from nanobot_ane.ane_inference import ANEInference

    with pytest.warns(DeprecationWarning):
        from nanobot_ane.service import ANEService

def test_new_imports_work():
    """New imports should work without warnings."""
    from memory_rolling_compression.mrc_backends.mrc_ane import MRCBackendANE
    from memory_rolling_compression.mrc_service import MRCService
```

### Backend Abstraction Tests

```python
# tests/mrc_backends/test_backend_interface.py

@pytest.mark.parametrize("backend_class", [
    MRCBackendANE,
    # MRCBackendAMDNPU,  # Future
    # MRCBackendGPU,  # Future
])
async def test_backend_interface(backend_class):
    """All backends must implement MRCBackend interface."""
    backend = backend_class(model_path=TEST_MODEL)

    await backend.load_model()
    result = await backend.infer("Test prompt", {"max_tokens": 50})
    assert isinstance(result, str)
    assert backend.backend_name
    assert backend.device_info
    await backend.unload_model()
```

### Integration Tests

```python
# tests/test_nanobot_integration.py

def test_mrc_client():
    """Nanobot integration should work with new names."""
    from memory_rolling_compression.mrc_client import MRCClient

    client = MRCClient("http://127.0.0.1:8766")
    # ... test requests
```

---

## Rollout Plan

### Timeline

| Week | Phase | Deliverables | Risk |
|------|-------|--------------|------|
| **Week 1** | Backend abstraction | backends/ structure, ANEBackend, tests | Low - additive only |
| **Week 2** | Core rename | Directory/file renames, update all refs | Medium - breaking changes |
| **Week 3** | Integration update | Nanobot patch, docs, examples | Low - external only |
| **Week 4** | Validation | Multi-platform testing, migration guide | Low - testing phase |

### Success Criteria

- [ ] All existing tests pass with new names
- [ ] Nanobot integration works identically
- [ ] Backend abstraction tested with mock backends
- [ ] Documentation reflects new architecture
- [ ] Migration guide complete and tested
- [ ] Zero regression in compression quality or performance

---

## Benefits Summary

### Technical

1. **Portability**: Works on any platform with NPU support
2. **Clarity**: Clear separation of NPU vs CPU operations
3. **Extensibility**: Easy to add new backends
4. **Correctness**: Better reflects actual hybrid architecture

### User-Facing

1. **Better naming**: "Rolling compression" describes what it does
2. **Platform support**: Opens door to Linux/Windows with AMD/Intel NPUs
3. **Flexibility**: Can use GPU fallback if no NPU available
4. **Future-proof**: Architecture ready for new NPU platforms

### Strategic

1. **Differentiation**: "Rolling compression" is a unique pattern, not "ANE copy"
2. **Portability claim**: Can demonstrate on multiple platforms
3. **Nanobot integration**: Better story ("universal compression" vs "Apple-only")
4. **Cross-pollination**: Can share with NPU project as generic pattern

---

## Open Questions

1. **Should we support CPU-only mode with mechanical merge?**
   - Pro: Maximum portability
   - Con: Lower quality, but still useful for testing/low-end

2. **Should we maintain `nanobot_ane` compatibility wrapper indefinitely?**
   - Pro: No breaking changes ever
   - Con: Tech debt, confusing two names

3. **Should we build AMD NPU backend now or wait?**
   - Pro: Validates abstraction, real multi-platform proof
   - Con: No AMD hardware to test on yet

4. **Rename entire repo `Anemll` → `RollingCompression`?**
   - Pro: Consistent top-to-bottom
   - Con: Very disruptive, breaks links/clones
   - Alternative: Keep repo name, rename subdirectory only

---

## Recommendation

**Proceed with phased rollout:**

1. **Week 1**: Add backends abstraction (non-breaking)
2. **Week 2**: Rename nanobot_ane → rolling_compression (document migration)
3. **Week 3**: Update nanobot integration
4. **Week 4**: Test and validate

**Defer:**
- AMD/Intel NPU backends (no hardware yet)
- CPU-only mode (questionable value)
- Full repo rename (too disruptive)

**Deliverable**: Clear, portable, well-architected rolling compression system that happens to use ANE on Apple hardware but isn't limited to it.

---

## Next Steps

1. **Review this plan** - feedback on approach
2. **Prioritize phases** - which parts are essential vs nice-to-have
3. **Create migration checklist** - detailed task list
4. **Start Week 1** - backend abstraction (safe, additive)

Would you like me to start implementing Phase 1 (backend abstraction)?
