# Cross-Pollination: AMD NPU (Hermes) → ANE (nanobot)

**Date**: 2026-11-05 (Updated: 2026-11-06)
**Source**: Influx934Threads/labtools - machines/gpu-beast/flm-npu-tests/rolling-compression
**Status**: ✅ **Budget 100 DEPLOYED TO PRODUCTION** (2026-11-06 19:53 UTC)

---

## 🚀 DEPLOYMENT UPDATE (2026-11-06 19:53 UTC)

**Budget 100 is now LIVE in production on ANE.**

**Deployment Details**:
- **Model**: Qwen3-4B (qwen3-4b-ctx2048)
- **Configuration**: Budget 100 per-turn extraction
- **Status**: Running (PID 1225)
- **Metrics**: http://127.0.0.1:8766/metrics
- **Performance**: 11.6x compression ratio (legacy data), awaiting new Budget 100 compressions

**Monitoring Commands**:
```bash
./anectl status
curl -s http://127.0.0.1:8766/metrics | jq '{model, configuration, compression_ratio, avg_extraction_tokens}'
```

**Documentation**:
- Deployment summary: `DEPLOYMENT_SUMMARY_20261106.md`
- Monitoring guide: `BUDGET_100_MONITORING_GUIDE.md`

---

## 🎯 CRITICAL UPDATE (2026-11-06): Budget 100 Breakthrough

**We achieved 100% recall on 4B where AMD's 4B failed — and now it's deployed in production.**

### The Discovery

After AMD reported that **4B models fail with token budgeting**, we conducted comprehensive multi-seed validation (seeds 101, 202, 303) and discovered:

**ANE Qwen3-4B + Budget 100 = 100% recall, ~42% token savings**

| Configuration | Recall Consistency | Savings | Seeds Tested |
|--------------|-------------------|---------|--------------|
| **ANE 4B + Budget 100** | **100% (3/3 seeds)** | **~42%** | 101, 202, 303 |
| AMD NPU 4B + Budget | 0% (failed) | N/A | Multiple |
| AMD NPU 9B + Budget | 100% | Significant | 3 seeds |

### Why This Matters for AMD

**Hypothesis**: 4B CAN work with proper budget constraint optimization. Key differences:

1. **Constraint tightness**: Our ≤100 token budget may be tighter than AMD's approach
2. **Model architecture**: Qwen3-4B vs Hermes-4B architectural differences
3. **Platform optimization**: ANE-specific optimizations vs AMD NPU

**Recommendation for AMD**: Retry 4B Hermes with strict Budget 100 constraint using our validated prompt:

```python
prompt = f"""Extract facts from this conversation turn. Target ≤100 tokens.
Be concise but clear. Abbreviate where unambiguous.
Preserve: numbers, percentages, file paths, specific names, measurements.

Turn:
{turn_text}

Facts (≤100 tokens):"""

max_tokens = 120  # 20% buffer
temperature = 0.0
```

**Multi-seed validation critical**: Our single-seed test (101) showed inconsistent chunk-size results. Seeds 202/303 revealed Budget 100's true consistency.

**See**: `arms/arm_d/BUDGET_100_VALIDATION.md` for complete analysis.

---

## Executive Summary

The AMD NPU + Hermes investigation (2026-10-30 → 2026-11-05) reached a NO-GO verdict due to synchronous timing constraints, but explicitly called out **nanobot_ane's async architecture as the solution they need**. They validated several of our ARM findings independently, and discovered optimization techniques we should adopt.

**Key insight from their closing**: *"The fix is architectural: redesign Hermes' compression trigger to run asynchronously in the background, the way the sibling Apple-ANE project (`nanobot_ane`) does it successfully."*

---

## Direct Validation of Our ARM Findings

### 1. Cost Ratio (ARM A) ✅ CONFIRMED

| Metric | AMD NPU | ANE |
|--------|---------|-----|
| Prefill speed | ~550 tok/s | 877.9 tok/s |
| Decode speed | ~14 tok/s | 26.8 tok/s |
| **Cost ratio** | **~39x** | **36.2x** |

**Finding**: Nearly identical cost structure validates that output token optimization is universal across NPU architectures.

**Relevance to us**: Our ARM A profiling correctly identified the optimization target.

---

### 2. Mechanical Merge (ARM C) ✅ INDEPENDENTLY VALIDATED

**AMD Finding**:
- Zero-LLM mechanical merge at CPU-level is the only viable reduce stage
- LLM-based reduce "never beat 5/8 recall" and was "non-monotonic" (better input → worse output)
- Quote: *"One abstraction pass is usable on this NPU; two is not."*

**ANE Implementation**:
- Deployed mechanical merge in production (commit 575db5c)
- 3,725x faster than LLM consolidation
- 93% recall vs 50% for LLM approach

**Cross-validation**: Two independent investigations on different hardware reached the identical conclusion.

---

### 3. Generative Selection (ARM E) ✅ ELEVATED TO "MOST CONSEQUENTIAL"

**AMD Finding**:
- Generative selection should replace embeddings as "general retrieval primitive"
- Quote: *"Possibly the most consequential item here"*
- Embedding retrieval (embed-gemma:300m) "condemned on evidence" - paraphrased queries scored at chance
- Generative extractive selection: 7/8 recall for ~27-30 output tokens, **flat cost** regardless of input size
- With 39x ratio, generation becomes CHEAPER than embedding for low-volume queries

**ANE Finding** (ARM E):
- Generative retrieval: 75% recall, 110 tokens per query
- Break-even: <137 queries/day (typical corpus)
- Decision pending usage analysis

**Cross-validation**: Both investigations independently discovered generative selection beats embeddings on NPU/ANE hardware.

**Action item**: Prioritize ARM E integration based on AMD's elevated importance assessment.

---

### 4. Token Budgeting (ARM D) ⚠️ UPDATED - 4B SUCCESS ON ANE

**AMD Findings** (2026-11-05):
- **4B models**: Token budgeting FAILS - causes hallucinations, unstable recall even with cues
- **9B models**: Token budgeting WORKS with proper cues
  - Budget 100 equivalent (chunk-size 32, 9B + cue): 8/8 recall, 3/3 seeds, fits budget
  - Required explicit prompt cues for content scanning

**ANE Findings** (Updated 2026-11-06):
- **1.7B model (Qwen3)**: Budget 100 provides 39% savings with 90-97% recall (FAILS perfect recall requirement)
- **4B model (Qwen3)**: ✅ **Budget 100 = 100% recall, ~42% savings** (VALIDATED 3/3 seeds)
  - Contradicts AMD's 4B failure
  - Tighter constraint (≤100 tokens) forces disciplined extraction
  - Natural language budget prompts work
- Structured formats (JSON, tags) cause 19-30% hallucinations

**Comparison** (UPDATED):

| Model Size | AMD NPU | ANE | Conclusion |
|------------|---------|-----|------------|
| 1.7B | Not tested | ❌ Budget 100: 90-97% recall | Below threshold |
| **4B** | ❌ Failed with budgets | ✅ **Budget 100: 100% recall** | **DIVERGENCE - Needs investigation** |
| 9B | ✅ Works with cues | ✅ chunk2: 100% recall, 37% savings | Both platforms validated |

**Key insight UPDATED**: Our Budget 100 success on 4B contradicts AMD's findings. Possible explanations:

1. **Constraint tightness matters**: ≤100 token hard limit vs AMD's approach
2. **Model differences**: Qwen3-4B vs Hermes-4B architecture
3. **Platform optimization**: ANE-specific benefits
4. **Prompt engineering**: Our exact wording may be critical

**Recommendation for AMD**: Retry Hermes-4B with our exact Budget 100 configuration and multi-seed validation methodology.

---

## New Optimization Techniques to Adopt

### 1. Chunk-Size Optimization ⚠️ UPDATED - NO ADDITIONAL VALUE ON ANE

**AMD Finding**: Chunk size (32-48 exchanges per chunk) was the ONLY lever that provided real token reduction without prompt engineering.

**Mechanism**:
- Each map call pays fixed overhead (heading boilerplate, instruction tokens)
- Fewer, larger chunks amortize this overhead
- **59-71% token reduction** vs baseline with zero recall cost (on 9B + cue)

**Best configuration**:
- 32 exchanges/chunk for 9B model
- 8 total chunks for 40K token conversation
- Required explicit aside-scanning cue to reach 8/8 recall

**ANE Testing Results** (2026-11-06):

We tested chunk-size optimization (chunk2, chunk4, chunk8) on ANE 4B with multi-seed validation:

| Configuration | Recall (3 seeds avg) | Savings vs Unconstrained | Status |
|--------------|---------------------|-------------------------|--------|
| Budget 100 (per-turn) | **100% (3/3)** | **~42%** | ✅ **OPTIMAL** |
| chunk2 (≈Budget 200) | 93% (2/3 failed seed 202) | ~42% | ❌ Inconsistent |
| chunk4 (≈Budget 400) | 93% (2/3 failed seed 202) | ~39% | ❌ Inconsistent |

**CRITICAL FINDING**: Chunk-size optimization adds **ZERO additional savings** over Budget 100 alone on ANE 4B:

- Budget 100 per-turn: ~42% savings, 100% recall
- chunk2/4 variants: Same ~42% savings, but **inconsistent recall** (failed seed 202)

**Why chunk-size fails on ANE**:
1. **Hidden baseline**: What we called "chunk1" already included Budget 100 constraint
2. **True baseline**: Unconstrained extraction (~9000 tokens) - Budget 100 provides all savings
3. **Larger budgets cause verbosity**: chunk2 (200 tokens) and chunk4 (400 tokens) allow model to ramble
4. **Tighter is better**: ≤100 token constraint forces discipline, preventing verbosity

**Conclusion for ANE**: ❌ **Do NOT adopt chunk-size optimization**. Budget 100 per-turn is simpler, more reliable, and achieves same savings.

**Divergence from AMD**: AMD's chunk32 success on 9B suggests this may be **model-size dependent** - works for larger models but not 4B on ANE.

---

### 2. Explicit Content-Scanning Cues ⭐ HIGH PRIORITY

**AMD Finding**: Adding explicit prompt cue rescued all missed facts:

```
"The transcript may contain short one-line asides or notices
(e.g. starting with 'Noting for the record:') embedded inside
unrelated code or debugging content. Scan for these specifically
-- do not let surrounding code crowd them out."
```

**Result**: 6/8 → 8/8 recall across all 3 seeds (zero misses)

**Root cause**: Model missed "context-orphaned asides" - short, important facts buried in unrelated code/noise.

**Application to ANE**:

Our fact extraction may miss similar "orphaned" critical facts. Add explicit cues:

```python
prompt = f"""Extract facts from this conversation turn. Target ≤100 tokens.
Be concise but clear. Abbreviate where unambiguous.

CRITICAL PRESERVATION:
- File paths (absolute and relative)
- Model names and version numbers
- Configuration values and parameters
- Error messages and status codes
- User preferences and decisions
- Short standalone observations (e.g., "Note:", "Important:", "Remember:")

Even if surrounded by unrelated content, scan for and preserve these specifically.

Turn:
{turn_text}

Facts (≤100 tokens):"""
```

**Expected benefit**: Reduce the 14% quality drop in Budget 100 by explicitly cueing for critical fact types.

---

### 3. Model Size Upgrade Path 🔮 FUTURE

**AMD Finding**: 9B model required for reliable token budgeting with cues.

**Current ANE**: Qwen3-1.7B (2048 context)

**Larger models available**:
- Qwen3-8B (ANE-optimized, already in Anemll repo)
- Could test Budget 100 on larger model

**Trade-off analysis needed**:
- Larger model = slower decode
- But if chunk-size optimization applies (fewer calls), total time may stay acceptable
- Background/async architecture gives us timing flexibility AMD didn't have

**Recommendation**: Low priority. Budget 100 already works acceptably on 1.7B. Only explore if quality requirements increase.

---

### 4. Async Architecture Validation ✅ CONFIRMED AS CRITICAL

**AMD's explicit finding**:

> "The fix is architectural, not another knob on this harness: redesign Hermes'
> compression trigger to run asynchronously in the background, the way the sibling
> Apple-ANE project (`nanobot_ane`) does it successfully — per-turn work there
> only has to fit the inter-turn gap, not a synchronous request/response window."

**Why AMD failed**:
- Hermes uses **global, synchronous** compression lock
- 300s ceiling enforced
- 9B model + chunk32 map stage takes **649-790s** (2.2-2.6x over limit)
- NO-GO verdict despite finding quality solution

**Why nanobot succeeds**:
- **Background, asynchronous** compression
- Per-turn work only needs to fit inter-turn idle gap
- No synchronous request/response constraint
- Can use slower, higher-quality approaches

**Validation**: Our async architecture is the KEY architectural advantage AMD identified as the solution.

**Action**: Document this as a core design principle. Any future work must preserve async architecture.

---

## Rejected Approaches (Do Not Re-Try)

AMD tested these extensively - all failed:

### 1. Rolling/Iterative Consolidation ❌
- **Why it fails**: Generational loss - each pass is a lossy copy of previous
- **Their verdict**: "Dies because each generation is a lossy copy of a lossy copy"
- **ANE status**: We don't use this (good decision)

### 2. Multi-Pass LLM Abstraction ❌
- **Why it fails**: Second LLM pass degrades output, non-monotonic
- **Their verdict**: "One abstraction pass is usable on this NPU; two is not"
- **ANE status**: We use single-pass extraction + mechanical merge (correct)

### 3. Structured Output Formats (JSON, indexed facts) ❌
- **Why it fails**: Model second-guesses itself, breaks JSON, fills with boilerplate
- **Their verdict**: "Any task asking this model to select or retain a subset of facts under token-budget pressure reliably keeps boilerplate-shaped content over real needles"
- **ANE status**: ARM D confirmed same (19-30% hallucinations) - avoid structured formats

### 4. Embedding Retrieval (for generative tasks) ❌
- **Why it fails**: Paraphrased queries score at chance
- **Their verdict**: "Condemned on evidence"
- **ANE status**: ARM E showed generative beats classical retrieval

---

## Divergences (Different Hardware/Model Behavior)

### 1. Decode Speed

| Metric | AMD NPU (4B) | ANE (1.7B) |
|--------|--------------|------------|
| Decode | ~14 tok/s | 26.8 tok/s |

ANE is ~1.9x faster at decode despite larger model class. This gives us more timing flexibility.

### 2. Model Size Requirements

- **AMD**: Required 9B for reliable token budgeting
- **ANE**: 1.7B achieves acceptable results with Budget 100

Possible reasons:
- Different model architectures (Qwen3 vs Qwen3.5)
- ANE's faster decode allows more generation budget
- Our async architecture removes timing pressure

---

## Recommended Actions for ANE

### Immediate (High ROI)

1. **Test Chunk-Size Optimization** ⭐⭐⭐
   - Extract facts over N-turn windows (2, 4, 8 turns)
   - Measure token reduction vs recall
   - Potential for 30-50% additional savings on top of Budget 100

2. **Add Explicit Content-Scanning Cues** ⭐⭐⭐
   - Update Budget 100 prompt with specific preservation instructions
   - Target: reduce 14% quality drop
   - Low-risk, high-reward prompt engineering

3. **Prioritize ARM E Integration** ⭐⭐
   - AMD elevated generative selection to "most consequential"
   - Our findings align with theirs
   - Remove embedding dependency, simplify architecture

### Medium-Term (Validation)

4. **Document Async Architecture as Design Principle**
   - AMD explicitly identified this as our key advantage
   - Ensure future work preserves this
   - Reference AMD's NO-GO as cautionary tale

5. **Test Chunked Extraction on Larger Models**
   - Qwen3-8B available in Anemll
   - Only if chunk-size optimization shows promise on 1.7B

### Low Priority (Exploration)

6. **Hybrid Chunk-Size Strategy**
   - Small chunks for critical turns (user decisions, errors)
   - Large chunks for routine conversations
   - Adaptive based on turn importance

---

## Cost Savings Projection

If we adopt chunk-size optimization with results similar to AMD's 59% reduction:

**Current Budget 100**:
- 251 → 153 tokens (39% savings)
- Cost: 5,539 token-equivalents @ 36.2x ratio

**Budget 100 + Chunk-Size (hypothetical)**:
- Apply 50% additional reduction: 153 × 0.5 = **~77 tokens**
- Cost: 2,787 token-equivalents @ 36.2x ratio
- **Total savings: 69% vs baseline**

**Caveat**: This is optimistic projection. Actual results depend on:
- Whether overhead amortization applies at nanobot's scale
- Recall preservation (must test rigorously)
- Our model size (1.7B vs their 9B)

---

## Lessons Learned

### What Worked (Both Projects)

1. ✅ **Mechanical merge** - Independently validated, zero-LLM consolidation
2. ✅ **Generative selection** - Both found it superior to embeddings
3. ✅ **Cost profiling** - ~36-39x ratio universal across NPU architectures
4. ✅ **Natural language prompts** - Beat structured formats on both platforms

### What's Model/Architecture-Specific

1. 🔀 **Token budgeting reliability** - Model size threshold exists (4B-9B range)
2. 🔀 **Decode speed** - ANE faster than AMD NPU at comparable model sizes
3. 🔀 **Async vs sync** - Architecture choice determines success/failure

### Critical Design Principles

1. **Async architecture is non-negotiable** - AMD's NO-GO proves this
2. **Single-pass extraction only** - Second LLM pass always degrades
3. **Mechanical merge for consolidation** - Zero-LLM beats LLM reduce
4. **Optimize output tokens, not input** - Universal NPU constraint

---

## AMD's Remaining Open Questions (Not Relevant to Us)

AMD identified these as next steps for their investigation:

1. **Dispatcher/routing optimization** - We don't have this role
2. **Turn ranking for 200+ exchanges** - Our sessions are smaller
3. **Device-level attractor fault** - AMD NPU hardware issue, not ANE

These are Hermes-specific or AMD-hardware-specific, not applicable to nanobot/ANE.

---

## References

### AMD NPU Investigation
- Repo: `Influx934Threads/labtools`
- Path: `machines/gpu-beast/flm-npu-tests/rolling-compression/`
- Key docs:
  - `ARCHITECTURE-I3-chunksize-20261104.md` - Full investigation narrative
  - `NPU-BEST-FIT-ENVELOPE.md` - Universal NPU constraints
  - `README.md` - Investigation overview

### ANE Investigation (Ours)
- Repo: `Influx934Threads/Anemll`
- Path: `nanobot_ane/arms/`
- Key docs:
  - `ARM_D_E_RESULTS.md` - ARM D & E findings
  - `2026-11-04-budget100-findings.md` - Budget 100 guide
  - `2026-11-04-arm-investigation-complete.md` - Complete ARM A-E summary

---

## Conclusion

The AMD NPU investigation provides strong validation of our ARM findings and identifies **chunk-size optimization** and **explicit content-scanning cues** as high-value additions. Most importantly, they explicitly identified **our async architecture as the solution they need**, validating it as a critical design advantage.

**Recommended next experiments**:
1. Test chunk-size optimization (2, 4, 8-turn windows)
2. Enhance Budget 100 with explicit preservation cues
3. Integrate ARM E (generative retrieval) based on AMD's priority assessment

These are low-risk, high-reward improvements backed by independent validation on different hardware.
