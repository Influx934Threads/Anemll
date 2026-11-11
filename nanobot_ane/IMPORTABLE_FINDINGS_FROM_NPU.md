# Importable Findings from NPU Rolling Compression

**Source**: `Influx934Threads/labtools/machines/gpu-beast/flm-npu-tests/rolling-compression/ARCHITECTURE-NPU-ROLLING-COMPRESSION.md`

**Date**: 2026-11-11

**Status**: Analysis complete - Ready for implementation planning

---

## Executive Summary

The NPU rolling compression project (Hermes agent with AMD NPU) is a **sibling project** to nanobot_ane that solves the same core problem: background context compression using NPU/ANE to avoid blocking the main model. Both projects have learned from each other, and the NPU project has now identified **6 critical production issues** that required fixes, some of which nanobot_ane should adopt proactively.

**Key Insight**: The NPU project explicitly credits nanobot_ane as the inspiration for its architecture redesign (§1.1: "This is a direct parallel to how `nanobot_ane` solves the same problem — background precompute, served from cache at request time").

---

## Critical Findings to Import (Priority: HIGH)

### 1. Degenerate Output Detection (Problem #2)

**Issue Discovered**: NPU "attractor" device fault causes degenerate output (`'!!!!!...'` repeated characters) that leaked into persisted facts through two code paths:
- Null-result boilerplate treated as real fact
- `_complete_sane`'s "always return something" contract trusted without degeneracy check

**Current Status in nanobot_ane**: ❌ **NOT IMPLEMENTED**
- No degenerate output detection
- No device fault handling
- Budget 100 validated on 3 seeds but no protection against hardware faults

**Recommended Implementation**:

```python
import re

# Pattern matching from NPU project
_NULL_RESULT_RE = re.compile(
    r'(no (new )?facts|nothing to extract|unable to|insufficient)',
    re.IGNORECASE
)

def is_degenerate(text: str, threshold: float = 0.3) -> bool:
    """
    Detect degenerate LLM output (device faults, repetitive garbage).

    Args:
        text: Output text to check
        threshold: If >30% of chars are the same repeated char, flag as degenerate

    Returns:
        True if text appears to be garbage/degenerate output
    """
    if not text or len(text) < 10:
        return True

    # Check for null-result phrases
    if _NULL_RESULT_RE.search(text):
        return True

    # Check for repetitive character patterns (attractor fault signature)
    # Count most common character
    from collections import Counter
    char_counts = Counter(c for c in text if c.isalnum())
    if char_counts:
        most_common_char, count = char_counts.most_common(1)[0]
        if count / len(text) > threshold:
            logger.warning(f"Degenerate output detected: '{most_common_char}' appears {count}/{len(text)} times")
            return True

    return False

# Apply at parse time AND after any give-up path
def extract_facts_safe(self, turn_text: str) -> str:
    """Extract facts with degenerate output protection."""
    result = self._extract_facts_raw(turn_text)

    if is_degenerate(result):
        logger.warning("Degenerate extraction detected, falling back to verbatim turn head")
        # Fallback: use first 100 tokens of turn verbatim
        return turn_text[:500]  # Rough approximation, adjust based on tokenizer

    return result
```

**Priority**: **HIGH** - Prevents data corruption from hardware faults
**Complexity**: Low - single utility function + call sites
**Risk**: None - pure defensive check

---

### 2. Lagged Checkpoint Serving (Problem #5 & #6)

**Issue Discovered**:
- **Problem #5**: Serving the live summary tip described turns still in nanobot's protected tail (wrong content)
- **Problem #6**: After compaction, there's a 12K token window where no checkpoint is old enough to serve → falls through to expensive main model

**Current Status in nanobot_ane**: ❌ **NOT IMPLEMENTED**
- No checkpoint concept at all
- `SessionSummary` has no `checkpoints` list
- Always serves live tip (same bug as NPU project had)

**Architecture Change Required**:

```python
@dataclass
class SessionSummary:
    """Rolling summary for a session"""
    text: str = ""
    facts: List[dict] = field(default_factory=list)
    turn_count: int = 0
    last_updated: datetime = field(default_factory=datetime.now)
    token_estimate: int = 0
    input_tokens: int = 0

    # NEW: Checkpoint history (Problem #5 fix)
    checkpoints: List[Dict[str, Any]] = field(default_factory=list)
    # Format: [{"turn_tokens": 5000, "text": "...", "facts": [...]}, ...]

# Configuration
SERVE_LAG_TOKENS = 12000  # From NPU project: conservative lag to avoid protected tail

def _consolidate_facts(self, session_key: str):
    """Consolidate facts AND record checkpoint."""
    # ... existing consolidation logic ...

    # NEW: Record checkpoint after consolidation
    summary = self.session_summaries[session_key]
    checkpoint = {
        "turn_tokens": summary.input_tokens,
        "text": summary.text,
        "facts": summary.facts.copy(),
        "timestamp": datetime.now().isoformat()
    }
    summary.checkpoints.append(checkpoint)

    # Limit checkpoint history (keep last 10)
    if len(summary.checkpoints) > 10:
        summary.checkpoints = summary.checkpoints[-10:]

def get_session_context(self, session_id: str) -> Optional[str]:
    """Get session context with lagged checkpoint serving."""
    summary = self.session_summaries.get(session_id)
    if not summary:
        return None

    # Serve newest checkpoint at least SERVE_LAG_TOKENS behind current tip
    current_tokens = summary.input_tokens
    for checkpoint in reversed(summary.checkpoints):
        lag = current_tokens - checkpoint["turn_tokens"]
        if lag >= SERVE_LAG_TOKENS:
            logger.debug(f"Serving lagged checkpoint: {lag} tokens behind tip")
            return checkpoint["text"]

    # No suitable checkpoint yet (Problem #6 scenario)
    # Could implement extract_on_demand here (see Finding #3)
    logger.debug("No checkpoint old enough to serve (need 12K lag)")
    return None  # or extract_on_demand(...)
```

**Priority**: **MEDIUM-HIGH** - Prevents serving wrong content but current system works
**Complexity**: Medium - requires checkpoint tracking + serving logic
**Risk**: Low - backwards compatible (empty checkpoints list = current behavior)

**Why This Matters for nanobot_ane**:
- Nanobot also has a protected tail concept (last N tokens kept verbatim during compaction)
- Serving live tip could describe content still in that tail
- Lagged checkpoint ensures we only serve facts from ALREADY COMPACTED turns

---

### 3. Extract-on-Demand Fallback (Problem #6 Fix)

**Issue Discovered**: After compaction boundary, first ~12K tokens have no checkpoint old enough to serve → every miss falls through to expensive thinker-model (80-345s), happening on a **predictable, recurring cadence**.

**Fix**: On miss, run extraction directly on request payload (5-30s, 10.7s observed) instead of falling through.

**Current Status in nanobot_ane**: ❌ **NOT IMPLEMENTED**
- No fallback extraction
- Cache miss = no context injection (silent fail-open)

**Architecture**:

```python
def extract_on_demand(self, messages: List[Dict]) -> Optional[str]:
    """
    Emergency extraction: run extraction directly on request payload.

    Used when:
    - No checkpoint old enough to serve (post-compaction window)
    - Session exists but checkpoint lag insufficient

    Returns compressed facts in 5-30s instead of falling through to main model.
    """
    if not messages:
        return None

    logger.info(f"Extract-on-demand: processing {len(messages)} messages")

    # Run same extraction pipeline as background ingestion
    extracted_facts = []
    for msg in messages:
        if msg.get("role") == "user":
            user_text = msg.get("content", "")
        elif msg.get("role") == "assistant":
            assistant_text = msg.get("content", "")
            turn_text = f"User: {user_text}\nAssistant: {assistant_text}"

            # Extract facts using Budget 100 prompt
            facts = self._extract_facts(turn_text)
            if facts and not is_degenerate(facts):
                extracted_facts.append(facts)

    if not extracted_facts:
        return None

    # One mechanical_consolidate pass
    consolidated = self.mechanical_merger.merge_facts(extracted_facts)

    logger.info(f"Extract-on-demand complete: {len(extracted_facts)} turns → {len(consolidated)} facts")
    return "\n".join(consolidated)

def get_session_context(self, session_id: str,
                       request_messages: Optional[List[Dict]] = None) -> Optional[str]:
    """Get session context with extract-on-demand fallback."""
    summary = self.session_summaries.get(session_id)
    if not summary:
        return None

    # Try lagged checkpoint first (Finding #2)
    current_tokens = summary.input_tokens
    for checkpoint in reversed(summary.checkpoints):
        lag = current_tokens - checkpoint["turn_tokens"]
        if lag >= SERVE_LAG_TOKENS:
            return checkpoint["text"]  # HIT

    # No suitable checkpoint - try extract-on-demand (Finding #3)
    if request_messages:
        logger.info("No lagged checkpoint available, attempting extract-on-demand")
        extracted = self.extract_on_demand(request_messages)
        if extracted:
            return extracted  # EXTRACT-FALLBACK HIT

    # True miss - no context available
    return None  # MISS
```

**Priority**: **MEDIUM** - Nice-to-have fallback for edge cases
**Complexity**: Medium - reuses existing extraction pipeline
**Risk**: Low - only triggers on miss path

**Metrics to Add**:
```python
@dataclass
class CompressionMetrics:
    # ... existing fields ...

    # Context serving metrics (NPU project pattern)
    cache_hits: int = 0              # Lagged checkpoint served
    extract_fallback_hits: int = 0   # On-demand extraction served
    cache_misses: int = 0            # No context available
```

---

## Findings Already Implemented

### 4. Budget 100 Token Strategy ✅

**Status**: ✅ **ALREADY IMPLEMENTED** in nanobot_ane (deployed 2026-11-06)

Both projects independently validated Budget 100 as optimal:
- NPU project: Mentioned as their compression strategy
- nanobot_ane: Validated with seeds 101, 202, 303 (100% recall, 42% savings)

**No action needed** - both projects converged on same solution.

---

### 5. Mechanical Merge (Zero-LLM Consolidation) ✅

**Status**: ✅ **ALREADY IMPLEMENTED** in nanobot_ane

NPU project: "ARM C: Mechanical merge (37% better than LLM)"
nanobot_ane: `arms/arm_c/mechanical_merger.py` with fuzzy dedup at 0.85 threshold

**No action needed** - nanobot_ane already uses this.

---

### 6. Background Precompute Architecture ✅

**Status**: ✅ **CORE ARCHITECTURE** of nanobot_ane

NPU project explicitly copied this from nanobot_ane (§1.1):
> "This is a direct parallel to how `nanobot_ane` solves the same problem — background precompute, served from cache at request time."

**No action needed** - this IS the nanobot_ane architecture.

---

## Findings Not Applicable

### 7. Streaming Response Support ❌ N/A

**NPU Project Issue**: Had to support both `stream=true` and `stream=false` (Problem #3)

**nanobot_ane Architecture**: Uses WebSocket for real-time updates, not HTTP streaming

**Decision**: Not applicable - different communication protocol

---

### 8. Session Affinity Key Resolution ❌ N/A

**NPU Project Issue**: Hermes sends derived hash keys (`gwk_<sha256(...)>`) instead of raw session IDs, requiring complex resolution logic

**nanobot_ane Architecture**: Direct session key from nanobot, no hashing

**Decision**: Not applicable - different session management

---

### 9. Compaction Boundary Detection (Partial)

**NPU Project Issue**: Hermes rewrites entire transcript with new row IDs on compaction, requiring special skip-floor logic (Problem #4)

**nanobot_ane Architecture**:
- Nanobot has compaction but different model (doesn't rewrite entire transcript)
- Background poll detects new turns incrementally
- No equivalent "transcript rewrite" event

**Decision**: Monitor for similar issues but likely not needed due to different compaction model

---

## Implementation Roadmap

### Phase 1: Defensive Measures (Week 1) - HIGH PRIORITY

1. **Degenerate Output Detection** (Finding #1)
   - Add `is_degenerate()` utility function
   - Apply to all extraction outputs
   - Add fallback to verbatim turn head
   - **Impact**: Prevents data corruption from hardware faults
   - **Effort**: 2-3 hours

### Phase 2: Quality Improvements (Week 2) - MEDIUM PRIORITY

2. **Lagged Checkpoint Serving** (Finding #2)
   - Add `checkpoints: List[Dict]` to `SessionSummary`
   - Record checkpoint on each consolidation
   - Implement lag-based serving in `get_session_context()`
   - **Impact**: Prevents serving content still in protected tail
   - **Effort**: 4-6 hours

3. **Extract-on-Demand Fallback** (Finding #3)
   - Implement `extract_on_demand()` method
   - Integrate into `get_session_context()` miss path
   - Add cache hit/miss metrics
   - **Impact**: Faster recovery from cache misses
   - **Effort**: 4-6 hours

### Phase 3: Monitoring (Week 3) - LOW PRIORITY

4. **Enhanced Metrics**
   - Add `cache_hits`, `extract_fallback_hits`, `cache_misses`
   - Update `/metrics` endpoint
   - Add `/status` endpoint mirroring NPU project's design
   - **Impact**: Better production observability
   - **Effort**: 2-3 hours

---

## Testing Strategy

For each finding:

1. **Unit Tests**:
   - `test_degenerate_detection()`: Various garbage patterns
   - `test_lagged_checkpoint_serving()`: Checkpoint selection logic
   - `test_extract_on_demand()`: Direct extraction path

2. **Integration Tests**:
   - Simulate hardware fault (inject degenerate output)
   - Simulate compaction boundary (checkpoint lag scenario)
   - Measure extract-on-demand latency

3. **Production Soak**:
   - Deploy with extensive logging
   - Monitor new metrics for 1 week
   - Validate no false positives on degeneracy detection

---

## Risk Assessment

| Finding | Implementation Risk | Production Risk if NOT Implemented |
|---------|--------------------|------------------------------------|
| #1 Degenerate Detection | **Low** - defensive check | **Medium** - data corruption from hardware faults |
| #2 Lagged Checkpoints | **Low** - backwards compatible | **Low** - edge case, current system works |
| #3 Extract-on-Demand | **Low** - fallback only | **Very Low** - graceful degradation already exists |

**Overall**: Low-risk, high-value improvements. Recommend implementing Finding #1 immediately, #2 and #3 in next sprint.

---

## Cross-Pollination Notes

This analysis demonstrates **successful cross-pollination** between sibling projects:

- **NPU → nanobot_ane**: Production lessons (degenerate detection, lagged checkpoints)
- **nanobot_ane → NPU**: Architecture pattern (background precompute, mentioned explicitly in NPU docs)
- **Both projects**: Converged independently on Budget 100 and mechanical merge

**Recommendation**: Establish regular cross-project review cadence to share production learnings.

---

## References

- Source Document: `Influx934Threads/labtools/machines/gpu-beast/flm-npu-tests/rolling-compression/ARCHITECTURE-NPU-ROLLING-COMPRESSION.md`
- Related Auto-Memory: `project_npu_rolling_compression_gonogo` (NPU project)
- Related Auto-Memory: `project_nanobot_ane_upstream_v2` (this project)
- nanobot_ane Deployment: `DEPLOYMENT_SUMMARY_20261106.md`
- nanobot_ane Production Config: `PRODUCTION_CONFIG.md`

---

## Appendix: NPU Project Timeline (For Context)

Understanding the NPU project's evolution helps contextualize these findings:

| Date | Phase | Key Event |
|------|-------|-----------|
| 2026-10-30 → 2026-11-05 | Phase 0 | Synchronous bulk compaction attempt (CLOSED NO-GO) |
| 2026-11-06 | Pivot | Architecture redesign inspired by nanobot_ane |
| 2026-11-10 | Phase 2 | Additive per-turn injection LIVE |
| 2026-11-10 | Phase 6 | Native-compaction short-circuit LIVE |
| 2026-11-10 18:44 | Problem #1 | GPU truncation → thinker timeout → 300s ceiling hit |
| 2026-11-10 (day 1) | Problems #2, #3 | Attractor fault, streaming response bug |
| 2026-11-11 (day 2) | Problems #4, #5 | Compaction rewrite handling, protected tail bug |
| 2026-11-11 12:20 | Problem #6 fix | Extract-on-demand confirmed (10.7s, zero thinker fallback) |

**Key Takeaway**: All 6 problems were discovered **in production** within 48 hours of deployment. These are not hypothetical - they are battle-tested fixes.
