# ARM D & E Execution Plan

**Date**: 2026-11-04
**Status**: Ready to Execute
**Prerequisites**: ✅ ARM A, B, C completed

## Overview

Continue the ARM investigation with:
- **ARM D**: Token budgeting to minimize output cost
- **ARM E**: Generative retrieval cost analysis

## ARM D: Output-Token Budgeting and Optimization

### Goal

Minimize output tokens in fact extraction while maintaining quality.

**Current state**: Fact extraction produces 94-215 tokens per turn (from ARM C test)

**Target**: Reduce to <75 tokens per turn without losing recall

### Hypothesis

Explicit token budgets in prompts reduce cost without hurting fact coverage.

### Test Strategy

Compare 5 prompt variants:
1. **Baseline** - Current prompt (no budget constraint)
2. **Soft budget** - "Keep output concise (aim for <75 tokens)"
3. **Hard budget** - "Output MUST be <75 tokens"
4. **Structured** - JSON format with type/content only
5. **Extreme** - "<50 tokens, essentials only"

### Metrics

For each variant measure:
- **Output tokens** (primary cost metric)
- **Quality score** (fact coverage, no hallucinations)
- **Coverage** (percentage of key facts extracted)
- **Hallucination rate** (facts not in source)

### Expected Outcome

Based on AMD findings:
- Structured format should reduce tokens 30-40%
- Hard budgets should hit target but may lose quality
- Soft budgets balance cost/quality

### Success Criteria

- ✅ Find variant with <75 tokens/turn AND >85% coverage
- ✅ No increase in hallucination rate
- ✅ Works across different conversation types

### Implementation Impact

If successful:
- Update fact extraction prompt in `service.py`
- Reduce per-turn cost by 30-50%
- Maintain or improve quality

### Execution Steps

```bash
cd /Users/agundez/Build/Anemll/nanobot_ane/arms/arm_d

# 1. Quick test (5 turns)
python3 test_token_budget.py --quick

# 2. Full test (20 turns)
python3 test_token_budget.py

# 3. Analyze results
# Results saved to: arms/results/arm_d_budget_results.json

# 4. Generate report
# Should show token savings vs quality tradeoff
```

### Time Estimate

- Quick test: ~2-3 minutes (5 turns × 5 variants)
- Full test: ~10-15 minutes (20 turns × 5 variants)
- Analysis: Manual review of results

### Files

- `arms/arm_d/test_token_budget.py` - Main test
- `arms/arm_d/prompt_variants.py` - Prompt variations
- `arms/arm_d/validator.py` - Quality validation
- Results: `arms/results/arm_d_budget_results.json`

---

## ARM E: Generative Selection as Primary Retrieval

### Goal

Determine cost of using generative selection for retrieval vs classical approaches.

### Context

**ARM B Results**:
- Classical BM25: 100% recall, 0 cost
- Generative selection: 75% recall, 94 tokens cost

**AMD Finding**: "Generative selection as this box's general retrieval primitive"

### Question

Is generative selection worth the cost for ANE-based retrieval?

### Test Strategy

Compare retrieval approaches on search queries:

1. **BM25 (baseline)**: Classical keyword search
2. **Generative selection**: LLM selects relevant turns
3. **Hybrid**: BM25 + generative reranking

### Metrics

- **Search quality**: Recall@k, Precision@k, MAP
- **Cost**: Output tokens per query
- **Latency**: Time per query
- **Context utilization**: Input tokens required

### Expected Findings

Based on ARM B:
- **BM25**: Free, fast, good for keyword queries
- **Generative**: Costly (94 tokens/query), better semantic understanding
- **Hybrid**: May offer best cost/quality balance

### Key Questions

1. **When is generative worth the cost?**
   - Complex semantic queries?
   - When context is critical?
   - Never (BM25 wins)?

2. **Can we optimize generative cost?**
   - Reduce prompt size?
   - Limit context window?
   - Use cheaper selection format?

3. **Should we use hybrid?**
   - BM25 for initial filtering
   - Generative for final selection
   - Reduces cost while improving quality?

### Success Criteria

- ✅ Cost analysis: tokens/query for each approach
- ✅ Quality analysis: recall/precision for each approach
- ✅ Recommendations: when to use generative vs classical

### Implementation Impact

**If generative wins**:
- Integrate generative retrieval in nanobot memory search
- Budget for output token cost in retrieval

**If classical wins** (likely based on ARM B):
- Stick with BM25 for retrieval
- Reserve generative for other tasks
- Document why AMD's finding doesn't apply to ANE

**If hybrid wins**:
- Implement two-stage retrieval
- BM25 first pass (free, fast)
- Generative rerank top-k (controlled cost)

### Execution Steps

```bash
cd /Users/agundez/Build/Anemll/nanobot_ane/arms/arm_e

# 1. Quick test (2 queries)
python3 test_generative_retrieval.py --quick

# 2. Full test (10 queries)
python3 test_generative_retrieval.py

# 3. Analyze cost vs quality tradeoff
# Results: arms/results/arm_e_retrieval_results.json
```

### Time Estimate

- Quick test: ~1-2 minutes (2 queries × 3 approaches)
- Full test: ~5-10 minutes (10 queries × 3 approaches)
- Analysis: Manual review

### Files

- `arms/arm_e/test_generative_retrieval.py` - Main test
- `arms/arm_e/generative_retriever.py` - Generative implementation
- Results: `arms/results/arm_e_retrieval_results.json`

---

## Execution Order

**Recommended sequence**:

1. **ARM D first** (more immediately actionable)
   - Directly reduces fact extraction cost
   - Can implement findings immediately in `service.py`
   - Lower risk, clear win expected

2. **ARM E second** (more exploratory)
   - Informs retrieval strategy decisions
   - May not have immediate implementation
   - Based on ARM B, classical likely wins for ANE

## Integration Timeline

### ARM D Integration (if successful)

**Immediate** (same session):
1. Identify best prompt variant
2. Update fact extraction prompt in `service.py`
3. Test with monitor tool
4. Commit changes

**Expected impact**:
- 30-50% reduction in fact extraction tokens
- Faster extraction (fewer tokens to generate)
- Same or better quality

### ARM E Integration (depends on findings)

**If generative wins** (unlikely based on ARM B):
- Design integration plan
- Requires more discussion on cost tradeoff

**If classical wins** (expected):
- Document findings
- Keep BM25 for retrieval
- No code changes needed

**If hybrid wins**:
- Prototype two-stage retrieval
- Test in production
- Measure cost savings

## Output Deliverables

### ARM D
- [x] Test results JSON
- [x] Token savings analysis
- [x] Prompt variant comparison
- [ ] Recommendation: which variant to use
- [ ] Updated `service.py` with best prompt
- [ ] Validation with monitor tool

### ARM E
- [x] Cost analysis (tokens per approach)
- [x] Quality analysis (recall/precision)
- [ ] Recommendation: when to use generative
- [ ] Decision: integrate or document
- [ ] If integrating: implementation plan

## Risk Assessment

### ARM D Risks

**Low risk**:
- Worst case: No improvement found, keep current prompt
- Medium case: Some improvement but quality drops
- Best case: Significant token savings with same quality

**Mitigation**:
- Validate with term loss measurement
- Test on real conversations before deploying
- Monitor quality metrics closely

### ARM E Risks

**Low risk** (informational):
- Just gathering data
- No immediate implementation required
- Can defer integration decision

## Next Steps After Completion

1. Update `INVESTIGATION_SUMMARY.md` with ARM D & E results
2. Update `README.md` with new findings
3. Commit all results to repository
4. Save to md-memories
5. Consider ARM F (if any follow-up investigations emerge)

## Questions to Answer

### ARM D
- What's the optimal token budget for fact extraction?
- Does structured JSON format reduce tokens?
- Can we get <75 tokens without quality loss?

### ARM E
- Is generative retrieval worth ~94 tokens per query on ANE?
- When should we use generative vs classical?
- Does hybrid approach make sense?

## Success Metrics

### Overall Success
- ✅ Both ARMs executed and analyzed
- ✅ Clear recommendations documented
- ✅ At least one finding integrated into production
- ✅ Results saved and committed

### ARM D Success
- ✅ Token reduction achieved (>20%)
- ✅ Quality maintained (>85% coverage)
- ✅ New prompt deployed in service.py

### ARM E Success
- ✅ Cost model documented for each approach
- ✅ Clear decision on retrieval strategy
- ✅ Findings compared to AMD results
