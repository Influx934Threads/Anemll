# EntityDeduplicator Test Plan

**Date**: 2026-11-12
**Goal**: Test entity-aware deduplication vs string-based deduplication
**Hypothesis**: EntityDeduplicator will correctly preserve facts with different numeric values

---

## Executive Summary

**Problem**: String-based deduplication (85% threshold) has 7.1% recall loss and would incorrectly merge short facts with different numbers (e.g., "timeout: 30s" vs "timeout: 60s" at 91.67% similarity).

**Proposed Solution**: EntityDeduplicator uses Jaccard similarity on extracted entities instead of raw string matching.

**Test Goal**: Determine if EntityDeduplicator:
1. ✅ Preserves facts with different numeric values (timeout 30s vs 60s)
2. ✅ Maintains or improves 92.9% recall
3. ✅ Achieves comparable compression (1.56x)
4. ⚠️ Doesn't over-preserve (compression too low)

---

## Current State: String-Based MechanicalMerger

### ARM C Test Results (Baseline)

| Metric | Value |
|--------|-------|
| Input facts | 14 |
| Output facts | 9 |
| Duplicates removed | 5 |
| Compression ratio | 1.56x |
| Recall | 92.9% (13/14 facts) |
| Time | 2ms |

### Known Issues

1. **High similarity despite different values**:
   - "timeout: 30s" vs "timeout: 60s" → 91.67% similar
   - Would merge at 85% threshold (loses different value)

2. **7.1% recall loss** (1 fact lost):
   - Unknown which fact gets lost
   - Need to investigate actual cause

---

## EntityDeduplicator Algorithm

### How It Works

```python
class EntityDeduplicator:
    """
    Extract entities (capitalized words, numbers) and compare using
    Jaccard similarity on entity sets instead of string similarity.
    """

    def deduplicate(facts):
        for each fact:
            1. Extract entities: numbers, capitalized words, units
            2. Compare entity set to all seen entity sets
            3. If Jaccard similarity > 50%, mark as duplicate
            4. Else keep as unique
```

### Example

```python
fact1 = "timeout: 30s"
  → entities = {"timeout", "30", "s"}

fact2 = "timeout: 60s"
  → entities = {"timeout", "60", "s"}

# Jaccard similarity
overlap = {"timeout", "s"} = 2 entities
union = {"timeout", "30", "60", "s"} = 4 entities
jaccard = 2/4 = 0.5 (50%)

# At 50% threshold: NOT duplicate → Keep both ✓
```

### Key Difference

| Approach | "timeout: 30s" vs "timeout: 60s" | Correct? |
|----------|----------------------------------|----------|
| **String-based (85%)** | 91.67% similar → Merge | ✗ Wrong |
| **Entity-based (50%)** | 50% Jaccard → Keep separate | ✓ Correct |

---

## Test Plan

### Phase 1: Unit Tests (Timeout Example)

**Test Case 1: Different numeric values should NOT merge**

```python
facts = [
    {"type": "configuration", "content": "timeout: 30s"},
    {"type": "configuration", "content": "timeout: 60s"},
]

# Expected with EntityDeduplicator:
#   → 2 unique facts (both preserved)

# Current MechanicalMerger result:
#   → 1 fact (merged incorrectly)
```

**Test Case 2: Same value rephrased SHOULD merge**

```python
facts = [
    {"type": "configuration", "content": "timeout configuration set to 30 seconds"},
    {"type": "configuration", "content": "timeout set to 30s"},
]

# Expected with EntityDeduplicator:
#   → 1 fact (correctly merged)
#   entity overlap: {"timeout", "30"} / {"timeout", "configuration", "set", "to", "30", "seconds", "s"}
#   Jaccard = low (different entity sets)
#
# Wait, this might NOT merge! Need to test.
```

**Test Case 3: API rate limit duplicates SHOULD merge**

```python
facts = [
    {"type": "configuration", "content": "API rate limit set to 100 requests per minute"},
    {"type": "configuration", "content": "API rate limit set to 100 requests per minute"},
    {"type": "configuration", "content": "API rate: 100 req/min"},
]

# Expected:
#   → 1-2 facts (first two identical, third might be separate)
```

### Phase 2: ARM C Dataset Test

**Objective**: Compare EntityDeduplicator vs MechanicalMerger on full ARM C data

**Test Script**: `tests/dev/test_entity_vs_string_dedup.py`

**Metrics to Measure**:

| Metric | String-based (baseline) | Entity-based (test) | Target |
|--------|------------------------|---------------------|--------|
| Input facts | 14 | 14 | - |
| Output facts | 9 | ? | 9-11 |
| Duplicates removed | 5 | ? | 3-5 |
| Compression ratio | 1.56x | ? | ≥1.3x |
| Recall | 92.9% | ? | ≥95% |
| Time (ms) | 2.2 | ? | <10 |

**Success Criteria**:
- ✅ Recall ≥ 95% (improves on 92.9%)
- ✅ Compression ≥ 1.3x (not too low)
- ✅ Preserves timeout 30s vs 60s separately
- ✅ Time < 10ms (acceptable for CPU-only)

### Phase 3: Edge Case Tests

**Edge Case 1: Very similar facts with different entity**

```python
facts = [
    {"type": "result", "content": "Changes applied successfully"},
    {"type": "result", "content": "Updates applied successfully"},
]

# entity sets: {"Changes"} vs {"Updates"}
# Jaccard = 0 / 2 = 0% → Keep separate
# String similarity = ~85% → Would merge

# Question: Should these merge or not?
# Answer: Probably yes (semantically same) - string-based is correct here
```

**Edge Case 2: Same entities, different meaning**

```python
facts = [
    {"type": "configuration", "content": "cache size increased from 512MB to 1024MB"},
    {"type": "configuration", "content": "cache size set to 1024MB"},
]

# entity sets: {"cache", "size", "512", "1024", "MB"} vs {"cache", "size", "1024", "MB"}
# Jaccard = 4/5 = 80% → Would merge
# String similarity = ~60% → Would NOT merge

# Question: Should these merge?
# Answer: Probably not (first has historical context)
```

**Edge Case 3: Numbers without units**

```python
facts = [
    {"type": "threshold", "content": "max retries set to 5"},
    {"type": "threshold", "content": "max retries set to 10"},
]

# entity sets: {"max", "retries", "set", "to", "5"} vs {"...", "10"}
# Jaccard = 4/6 = 67% → Would merge at 50% threshold!
# String similarity = ~85% → Would merge too

# Both approaches fail here!
```

---

## Implementation Steps

### Step 1: Create Test Script

**File**: `tests/dev/test_entity_vs_string_dedup.py`

```python
#!/usr/bin/env python3
"""
Compare EntityDeduplicator vs MechanicalMerger (string-based)
on ARM C dataset and specific test cases
"""

def test_timeout_case():
    """Test the critical timeout 30s vs 60s case"""
    # Use both deduplicators
    # Compare results
    pass

def test_arm_c_dataset():
    """Run both on full ARM C data"""
    # Load 14 facts from ARM C
    # Run MechanicalMerger (baseline)
    # Run EntityDeduplicator
    # Compare metrics
    pass

def test_edge_cases():
    """Test edge cases where approaches differ"""
    pass
```

### Step 2: Run Tests

```bash
cd /Users/agundez/Build/Anemll/nanobot_ane
python3 tests/dev/test_entity_vs_string_dedup.py
```

### Step 3: Analyze Results

Create comparison table:
- Recall improvement
- Compression trade-off
- Specific cases where entity-based wins
- Specific cases where string-based wins

### Step 4: Decision

Based on test results:

**If entity-based is clearly better** (recall >95%, compression >1.3x):
  → Adopt EntityDeduplicator as default

**If entity-based is mixed** (better recall, worse compression):
  → Make it configurable:
  ```python
  MechanicalMerger(mode="string", threshold=0.85)  # Current
  MechanicalMerger(mode="entity", threshold=0.50)  # New
  MechanicalMerger(mode="hybrid")                   # Both
  ```

**If entity-based is worse** (lower recall, similar compression):
  → Keep string-based, document entity-based as alternative for specific use cases

---

## Hybrid Approach (If Needed)

If neither approach is clearly superior, consider hybrid:

```python
class HybridDeduplicator:
    """
    Use entity-based for configuration/threshold facts (where numbers matter)
    Use string-based for result/context facts (where phrasing varies)
    """

    def deduplicate(self, facts):
        grouped_by_type = group(facts)

        for fact_type, fact_list in grouped_by_type:
            if fact_type in ["configuration", "threshold", "number"]:
                # Use entity-based (preserves different values)
                unique = EntityDeduplicator().deduplicate(fact_list)
            else:
                # Use string-based (better for rephrasing)
                unique = StringDeduplicator(0.85).deduplicate(fact_list)

        return merge_all(unique_lists)
```

---

## Expected Outcomes

### Scenario A: EntityDeduplicator Wins

**Results**:
- Recall: 92.9% → 100% (all facts preserved)
- Compression: 1.56x → 1.4x (less aggressive merging)
- Timeout 30s vs 60s: Correctly kept separate ✓

**Action**:
1. Replace MechanicalMerger with EntityDeduplicator
2. Update CPU-only backend to use entity-based dedup
3. Document improvement in recall

### Scenario B: Trade-offs Exist

**Results**:
- Recall: 92.9% → 96% (better, but not perfect)
- Compression: 1.56x → 1.2x (noticeably lower)
- Some cases entity-based wins, some string-based wins

**Action**:
1. Make deduplication strategy configurable
2. Default to hybrid approach
3. Allow users to choose based on their needs:
   - High precision: entity-based
   - High compression: string-based

### Scenario C: EntityDeduplicator Has Issues

**Results**:
- Recall: 92.9% → 90% (worse!)
- Compression: 1.56x → 1.1x (too low)
- Entity extraction misses key similarities

**Action**:
1. Keep string-based MechanicalMerger
2. Improve entity extraction patterns
3. Retest after improvements
4. Consider hybrid only for numeric facts

---

## Risk Assessment

### Risk 1: Over-Preservation

**Risk**: Entity-based might keep too many duplicates (low compression)

**Mitigation**:
- Test with multiple Jaccard thresholds (40%, 50%, 60%)
- Compare compression vs recall trade-off
- Accept slightly lower compression for better accuracy

### Risk 2: Entity Extraction Quality

**Risk**: Regex patterns might miss entities or extract noise

**Mitigation**:
- Review entity extraction on sample facts
- Add unit tests for entity extraction
- Improve patterns based on test failures

### Risk 3: Performance

**Risk**: Entity extraction + Jaccard might be slower than string matching

**Mitigation**:
- Benchmark both approaches
- Target: <10ms for 14 facts (acceptable)
- If too slow, optimize entity extraction

---

## Success Metrics

### Must Have
- ✅ Preserves timeout 30s vs 60s separately
- ✅ Recall ≥ 95% (better than 92.9%)
- ✅ Time < 10ms (acceptable for CPU-only)

### Nice to Have
- ✅ Compression ≥ 1.5x (maintains current level)
- ✅ Clearer error patterns (know why facts merge/don't merge)
- ✅ Configurable for different use cases

### Acceptable Trade-offs
- ⚠️ Compression 1.3-1.5x (vs 1.56x) if recall improves
- ⚠️ Time 5-10ms (vs 2ms) if recall improves significantly

---

## Timeline

**Phase 1: Unit Tests** (1-2 hours)
- Create test_entity_vs_string_dedup.py
- Test timeout case, API rate limit case
- Verify entity extraction works correctly

**Phase 2: ARM C Dataset Test** (1 hour)
- Run on full 14-fact dataset
- Compare metrics
- Identify wins/losses

**Phase 3: Analysis** (1 hour)
- Create comparison table
- Document edge cases
- Make recommendation

**Phase 4: Integration** (2-3 hours, if adopted)
- Update MechanicalMerger or add configuration
- Update CPU-only backend plan
- Add tests to arms/arm_c/test_map_merge.py
- Document in ROLLING_COMPRESSION_REFACTOR_PLAN.md

**Total**: 5-7 hours of work

---

## Next Steps

1. ✅ Create `tests/dev/test_entity_vs_string_dedup.py` test script
2. ✅ Run timeout case tests (unit test)
3. ✅ Run ARM C dataset comparison
4. ✅ Analyze results and create recommendation
5. ⏳ Update refactoring plan based on findings

Ready to proceed?
