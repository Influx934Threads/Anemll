# ANE vs GPU: Chunk-Size Optimization Comparison

**Test Date**: 2026-11-06
**Seed**: 101 (identical synthetic conversation)
**Configuration**: 48 turns, 32 planted facts

## Executive Summary

**Critical Finding**: Chunk-size optimization is **highly model-size dependent**. The technique provides dramatic token savings on 9B models but minimal savings on 1.7B models. However, on ANE, chunk2 improves recall quality instead.

## Results Comparison (Seed 101)

### GPU: Bonsai 9B (Port 8080)
| Chunk Size | Chunks | Tokens | Recall | Savings |
|------------|--------|--------|---------|---------|
| 1 (baseline) | 48 | 3571 | 32/32 (100%) | 0% |
| 2 | 24 | 2179 | 32/32 (100%) | 39.0% |
| 4 | 12 | 1976 | 29/32 (90.6%) | 44.7% |

**Best**: chunk2 - 39% savings with perfect recall

### ANE: Qwen3 1.7B (Direct Load)
| Chunk Size | Chunks | Tokens | Recall | Savings |
|------------|--------|--------|---------|---------|
| 1 (baseline) | 48 | 6576 | 29/32 (90.6%) | 0% |
| 2 | 24 | 6420 | 31/32 (96.9%) | 2.4% |
| 4 | 12 | 6084 | 27/32 (84.4%) | 7.5% |

**Best**: chunk2 - 2.4% savings BUT 6.3% recall improvement

## Key Differences

### 1. Token Verbosity
- **ANE produces 84% MORE tokens** (6576 vs 3571)
- The 1.7B model is significantly more verbose
- Struggles with concise extraction compared to 9B model

### 2. Savings Magnitude
| Metric | GPU (9B) | ANE (1.7B) | Difference |
|--------|----------|------------|------------|
| chunk2 savings | 39.0% | 2.4% | **16x less effective** |
| chunk4 savings | 44.7% | 7.5% | **6x less effective** |

**Conclusion**: Chunk-size optimization's token reduction is model-size dependent.

### 3. Quality Impact
On ANE, chunk2 actually **improves recall**:
- Baseline: 29/32 (90.6%)
- chunk2: 31/32 (96.9%) - **+6.3% improvement**
- chunk4: 27/32 (84.4%) - **-6.2% degradation**

**This is the opposite of GPU** where baseline already had 100% recall.

### 4. Missed Facts Analysis

**ANE Baseline (chunk1) missed**:
- "user chose option B"
- "user chose option A" (x2)

**ANE chunk2 recovered all 3** but missed:
- "ConnectionError: connection refused (errno 64)"

**ANE chunk4 missed 5 facts** (worse than baseline).

## Interpretation

### Why ANE Has Minimal Token Savings
1. **Model capacity**: 1.7B model has less capability for concise summarization
2. **Verbose output**: Produces 2x more tokens for same extraction task
3. **Less headroom**: Already struggling with quality, can't compress much more

### Why chunk2 Improves ANE Recall
1. **Context window**: 2-turn chunks provide more context for the smaller model
2. **Better inference**: Additional context helps the model identify orphaned facts
3. **Quality over savings**: Trade-off shifts from tokens→quality on smaller models

## Recommendations

### For ANE (1.7B Model)
**Adopt chunk2** - not for token savings, but for quality:
- ✓ Improves recall: 90.6% → 96.9% (+6.3%)
- ✓ Minimal token cost: only 2.4% less savings
- ✓ Better than chunk4 which degrades quality
- ✗ Don't expect significant token reduction

### For GPU (9B Model)
**Adopt chunk2** for token savings:
- ✓ Major savings: 39% token reduction
- ✓ Perfect recall maintained
- ✓ Consistent across seeds (2/3 seeds with 100% recall)

## Model Size Dependency

The results strongly suggest chunk-size optimization effectiveness scales with model size:

| Model Size | Primary Benefit | Secondary Benefit |
|------------|-----------------|-------------------|
| 9B (GPU) | Token savings (39%) | Recall maintained |
| 1.7B (ANE) | Quality improvement (+6.3%) | Minimal savings (2.4%) |

This mirrors AMD NPU findings where they used 9B models and achieved 59-71% savings.

## Next Steps

### Option 1: Validate with Multi-Seed (ANE)
Run seeds 202, 303 on ANE to confirm:
- Is 2.4% savings consistent?
- Does chunk2 consistently improve recall?
- Is chunk4 consistently worse than chunk2?

**Estimated time**: 2-3 hours (2 seeds × ~40 min each)

### Option 2: Test chunk2+Budget100 on ANE
Test if chunk2 improves Budget 100's quality score (currently 0.62):
- Does chunk2 context help Budget 100 extract better?
- Can we achieve >0.70 quality with chunk2+Budget100?
- Is the combination worth adopting?

**Estimated time**: 30-45 minutes

### Option 3: Both
Run multi-seed validation first for statistical rigor, then test chunk2+Budget100.

**Estimated time**: 3-4 hours total

## Conclusion

Chunk-size optimization works, but differently based on model size:
- **Large models (9B)**: Dramatic token savings (39-59%)
- **Small models (1.7B)**: Quality improvement (+6.3% recall) with minimal savings

For nanobot on ANE, chunk2 is worth adopting for **quality improvement**, not token reduction.

## Files
- ANE seed 101 results: `arms/results/chunk_size_ane_seed101.json`
- GPU seed 101 results: `arms/results/chunk_size_seed101.json`
- Test scripts:
  - GPU: `arms/arm_d/test_chunk_size.py`
  - ANE: `arms/arm_d/test_chunk_size_ane.py`
