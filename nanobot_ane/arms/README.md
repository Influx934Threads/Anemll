# NPU Best-Fit Envelope Investigation - ARM Testing Suite

Comprehensive investigation of Apple ANE characteristics and optimization strategies, inspired by AMD XDNA2 NPU findings documented in `~/Build/NPU-BEST-FIT-ENVELOPE.md`.

## Overview

This investigation consists of 5 independent test arms (A-E), each exploring a specific optimization strategy validated on AMD's NPU and adapted for Apple ANE.

## Quick Start

```bash
# Ensure you're in the nanobot_ane directory
cd /Users/agundez/Build/Anemll/nanobot_ane

# Run all arms sequentially (recommended for first run)
./run_all_arms.sh

# Or run individual arms (see below)
```

## Test Arms

### ARM A: ANE Characteristics Profiling

**Goal:** Measure prefill vs decode performance to find ANE's cost asymmetry ratio.

**AMD Finding:** 39x cost ratio (prefill ~550 tok/s, decode ~14 tok/s) → optimize for output tokens

**Run:**
```bash
python arms/arm_a/test_ane_profile.py

# Quick mode (reduced test matrix)
python arms/arm_a/test_ane_profile.py --quick

# Analyze results
python arms/arm_a/analyze_results.py
```

**Outputs:**
- `arms/results/arm_a_profile_results.json` - Raw measurements
- `arms/results/arm_a_analysis.md` - Human-readable report

**Key Metrics:**
- Prefill speed (tok/s)
- Decode speed (tok/s)
- Cost ratio (output/input token cost)
- ANE's best-fit envelope

---

### ARM B: Generative Selection (Extractive ID Emission)

**Goal:** Test if generative ID selection beats classical rankers when cost is measured in output tokens.

**AMD Finding:** 7/8 recall for ~27 output tokens (flat cost regardless of input size)

**Run:**
```bash
python arms/arm_b/test_generative_selection.py

# Quick mode
python arms/arm_b/test_generative_selection.py --quick
```

**Outputs:**
- `arms/results/arm_b_selection_results.json`

**Compares:**
- Generative selector (emits turn IDs)
- BM25 ranker (classical)
- TF-IDF ranker (classical)

**Key Metrics:**
- Recall@10
- Precision@10
- Mean Average Precision
- Output tokens (generative only)

---

### ARM C: Map-Mechanical-Merge Pattern

**Goal:** Replace LLM consolidation (every 5 turns) with CPU-side mechanical merging.

**AMD Finding:** Second LLM pass (reduce) never beat 5/8 recall and was non-monotonic → avoid multi-pass abstraction

**Run:**
```bash
python arms/arm_c/test_map_merge.py

# Quick mode (5 turns)
python arms/arm_c/test_map_merge.py --quick
```

**Outputs:**
- `arms/results/arm_c_merge_results.json`

**Compares:**
- Current approach: Extract facts (LLM) + Consolidate (LLM)
- New approach: Extract facts (LLM) + Mechanical merge (CPU)

**Key Metrics:**
- Total time (extraction + merge)
- Recall (fact preservation)
- Duplicate removal effectiveness

---

### ARM D: Output-Token Budgeting and Optimization

**Goal:** Minimize output tokens while maintaining quality through prompt engineering.

**AMD Finding:** Output tokens cost 39x input tokens → explicit budgets critical

**Run:**
```bash
python arms/arm_d/test_token_budget.py

# Quick mode (5 turns)
python arms/arm_d/test_token_budget.py --quick
```

**Outputs:**
- `arms/results/arm_d_budget_results.json`

**Tests 6 prompt variants:**
1. **Baseline** - Current prompts (no budget)
2. **D1 Strict** - Hard ≤50 token limit
3. **D2 JSON** - Structured JSON output
4. **D3 Entity IDs** - ID mapping (max compression)
5. **D4 Tagged** - Type-tagged facts
6. **D5 Bullets** - Ultra-concise bullets

**Key Metrics:**
- Average output tokens
- Quality score (entity/number coverage)
- Hallucination rate
- Token reduction vs baseline

---

### ARM E: Generative Selection as Primary Retrieval (Bonus)

**Goal:** Determine if generative selection should replace embeddings entirely.

**AMD Finding:** Embeddings failed (paraphrase queries at chance), generative succeeded → consider replacing embeddings altogether

**Run:**
```bash
python arms/arm_e/test_generative_retrieval.py

# Quick mode
python arms/arm_e/test_generative_retrieval.py --quick
```

**Outputs:**
- `arms/results/arm_e_retrieval_results.json`

**Analyzes:**
- Retrieval quality (recall, precision)
- Cost modeling (generative vs embedding)
- Break-even point (queries/day)

**Key Metrics:**
- Recall@10 on real queries
- Cost comparison across scenarios
- When generative beats embeddings

---

## Directory Structure

```
arms/
├── README.md                      # This file
├── shared/                        # Shared infrastructure
│   ├── __init__.py
│   ├── metrics.py                 # Measurement utilities
│   ├── fixtures.py                # Test data generators
│   └── fixtures/                  # Generated test data
│       ├── conversation_small.json
│       ├── conversation_medium.json
│       ├── conversation_large.json
│       ├── facts_labeled.json
│       └── queries_labeled.json
│
├── arm_a/                         # ANE Profiling
│   ├── __init__.py
│   ├── profiler.py                # Instrumented ANE inference
│   ├── test_ane_profile.py        # Test harness
│   └── analyze_results.py         # Analysis script
│
├── arm_b/                         # Generative Selection
│   ├── __init__.py
│   ├── selector.py                # Generative ID selector
│   ├── baseline_ranker.py         # BM25/TF-IDF baselines
│   └── test_generative_selection.py
│
├── arm_c/                         # Map-Mechanical-Merge
│   ├── __init__.py
│   ├── mechanical_merger.py       # Zero-LLM merging
│   ├── structured_extractor.py    # Structured fact extraction
│   └── test_map_merge.py
│
├── arm_d/                         # Token Budgeting
│   ├── __init__.py
│   ├── prompt_variants.py         # 6 prompt strategies
│   ├── validator.py               # Quality validation
│   └── test_token_budget.py
│
├── arm_e/                         # Generative Retrieval
│   ├── __init__.py
│   ├── generative_retriever.py    # Retrieval interface
│   └── test_generative_retrieval.py
│
└── results/                       # JSON results and markdown reports
    ├── arm_a_profile_results.json
    ├── arm_a_analysis.md
    ├── arm_b_selection_results.json
    ├── arm_c_merge_results.json
    ├── arm_d_budget_results.json
    └── arm_e_retrieval_results.json
```

## Dependencies

All arms use:
- `ane_inference.py` (existing nanobot_ane ANE inference)
- `arms/shared/` (common metrics and fixtures)

No additional dependencies beyond nanobot_ane requirements.

## Running All Arms

Create `run_all_arms.sh` in the `arms/` directory:

```bash
#!/bin/bash
# Run all investigation arms sequentially

set -e  # Exit on error

MODEL_PATH="${MODEL_PATH:-~/.nanobot/models/qwen3-1.7b/qwen3-ane-instruct.mlmodelc}"

echo "========================================"
echo "NPU Best-Fit Envelope Investigation"
echo "========================================"
echo ""
echo "Model: $MODEL_PATH"
echo ""

# ARM A: Profiling
echo "=== ARM A: ANE Profiling ==="
python arms/arm_a/test_ane_profile.py --model "$MODEL_PATH" --quick
python arms/arm_a/analyze_results.py
echo ""

# ARM B: Generative Selection
echo "=== ARM B: Generative Selection ==="
python arms/arm_b/test_generative_selection.py --model "$MODEL_PATH" --quick
echo ""

# ARM C: Map-Mechanical-Merge
echo "=== ARM C: Map-Mechanical-Merge ==="
python arms/arm_c/test_map_merge.py --model "$MODEL_PATH" --quick
echo ""

# ARM D: Token Budgeting
echo "=== ARM D: Token Budgeting ==="
python arms/arm_d/test_token_budget.py --model "$MODEL_PATH" --quick
echo ""

# ARM E: Generative Retrieval
echo "=== ARM E: Generative Retrieval ==="
python arms/arm_e/test_generative_retrieval.py --model "$MODEL_PATH" --quick
echo ""

echo "========================================"
echo "All arms complete!"
echo "========================================"
echo ""
echo "Results saved to arms/results/"
echo ""
echo "Next steps:"
echo "  1. Review results in arms/results/"
echo "  2. Read analysis reports (*.md files)"
echo "  3. Check INTEGRATION_RECOMMENDATION.md for next actions"
```

## Interpreting Results

### ARM A Success Criteria

- Cost ratio measured with <5% variance
- Time prediction accuracy within 5%
- ANE envelope identified

**If cost ratio > 10x:** ARM B, C, D are HIGH PRIORITY (output optimization critical)
**If cost ratio 5-10x:** ARM B, C, D are MEDIUM PRIORITY
**If cost ratio < 5x:** Reassess strategy before other arms

### ARM B Success Criteria

- Recall@10 >= current baseline
- Output tokens < 50 (vs 100-150 for fact extraction)
- Cost flat in input size

**Winner:** Generative selector if recall is competitive and tokens < 50

### ARM C Success Criteria

- Recall >= 95% of LLM consolidation baseline
- Time savings >= 25%
- Duplicate removal within 10% of LLM baseline

**Winner:** Mechanical merge if time savings > 20% and recall drop < 10%

### ARM D Success Criteria

- Token reduction >= 40% vs baseline
- Fact coverage >= 90%
- Hallucination rate <= 5%

**Winner:** Prompt variant with best token/quality tradeoff

### ARM E Success Criteria

- Recall >= 80% on real queries
- Cost break-even point identified
- Latency acceptable (<5s per query)

**Winner:** Generative if it wins on cost at realistic query volumes

## Integration Workflow

1. **Run ARM A first** - Determines if other arms are worth pursuing
2. **If ARM A shows >10x ratio:**
   - Run ARM B, C, D (high priority)
   - Run ARM E (optional)
3. **If ARM A shows 5-10x ratio:**
   - Run ARM B, C, D (medium priority)
   - Skip ARM E
4. **If ARM A shows <5x ratio:**
   - Reassess approach
   - AMD learnings may not transfer

## Expected Timeline

- **Quick mode (all arms):** ~30-60 minutes
- **Full mode (all arms):** ~4-6 hours (mostly ARM A profiling)

## Troubleshooting

**Model not found:**
```bash
# Specify custom model path
export MODEL_PATH=/path/to/your/model.mlmodelc
python arms/arm_a/test_ane_profile.py --model "$MODEL_PATH"
```

**Import errors:**
```bash
# Ensure you're in the nanobot_ane directory
cd /Users/agundez/Build/Anemll/nanobot_ane

# Check Python path
python -c "import sys; print(sys.path)"
```

**Fixture generation errors:**
```bash
# Regenerate fixtures
cd arms/shared
python -c "from fixtures import Fixtures; f = Fixtures(); f.get_conversation('medium')"
```

## References

- **AMD NPU Investigation:** `~/Build/NPU-BEST-FIT-ENVELOPE.md`
- **Investigation Plan:** `NPU_INVESTIGATION_PLAN.md`
- **nanobot_ane Architecture:** `MEMORY_ARCHITECTURE.md`
- **Current Prompts:** `NANOBOT_ANE_PROMPTS.md`

## Contributing

To add a new test arm:

1. Create `arms/arm_X/` directory
2. Implement test harness as `test_*.py`
3. Add to `run_all_arms.sh`
4. Document in this README

## License

Same as nanobot_ane project.
