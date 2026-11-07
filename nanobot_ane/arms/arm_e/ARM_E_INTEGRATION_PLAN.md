# ARM E Integration Plan: Generative Retrieval

**Date**: 2026-11-05
**Status**: Planning phase
**Priority**: HIGH (elevated by AMD NPU investigation)

---

## Executive Summary

Integrate generative selection as the primary retrieval mechanism for nanobot, replacing or supplementing classical BM25 retrieval. AMD NPU investigation elevated this to **"possibly the most consequential item"** and "condemned embeddings on evidence."

**Decision criteria**: Adopt if query volume <137 queries/day (median break-even point).

---

## Motivation (AMD NPU Validation)

### AMD's Finding

> "Generative selection as this box's general retrieval primitive — possibly
> the most consequential item here. Embedding retrieval here is condemned on
> evidence: `embed-gemma:300m` put realistic paraphrase queries at chance in
> all four grid cells. Meanwhile extractive ID-selection scored 7/8 for 27
> output tokens and its cost is flat in input."

### Key Arguments

1. **Embedding fails on paraphrased queries** - AMD found chance-level recall
2. **Generative cost is flat** - ~27-30 tokens regardless of corpus size
3. **NPU cost ratio favors generation** - 39x (AMD) / 36.2x (ANE) ratio makes flat-output-cost approaches win
4. **Architectural simplification** - Removes embedding service dependency

### Our ARM E Findings

- **Quality**: 75% recall@10 (acceptable, ≥70% threshold)
- **Cost**: 110 tokens per query
- **Time**: ~7 seconds per query
- **Break-even**: <137 queries/day (typical corpus)

---

## Current nanobot Architecture

### Retrieval in nanobot

Currently, nanobot uses:
1. **BM25 for fact retrieval** - Classical keyword-based search
2. **No embedding service** - Simplified architecture (good)
3. **Session-based memory** - Facts stored per session in `ane_state.json`

### ANE Compression Service (service.py)

Current flow:
```
User turn → Fact extraction → Store in session facts →
(on consolidation) → Mechanical merge → Summary storage
```

Retrieval happens when:
- User asks about past conversation
- Service needs to find relevant context for current turn

---

## Integration Options

### Option 1: Replace BM25 with Generative (Full Replacement)

**Architecture**:
```python
class ANEService:
    def __init__(self, model_path: str):
        self.inference = ANEInference(model_path)
        self.retriever = GenerativeRetriever(model_path)  # NEW
        # Remove: BM25 indexer

    async def retrieve_facts(self, query: str, session_id: str) -> list[dict]:
        """Retrieve relevant facts using generative selection"""
        facts = self._get_session_facts(session_id)
        relevant_facts, metrics = self.retriever.search_facts(query, facts, k=10)
        return relevant_facts
```

**Pros**:
- Simplest architecture
- Best semantic understanding
- No embedding infrastructure

**Cons**:
- ~7s latency per query
- Only viable if <137 queries/day
- No fallback if generative fails

---

### Option 2: Hybrid (Generative + BM25 fallback)

**Architecture**:
```python
class ANEService:
    def __init__(self, model_path: str):
        self.inference = ANEInference(model_path)
        self.generative_retriever = GenerativeRetriever(model_path)
        self.bm25_retriever = BM25Retriever()  # Keep existing
        self.retrieval_mode = "generative"  # or "bm25", "hybrid"

    async def retrieve_facts(self, query: str, session_id: str) -> list[dict]:
        """Retrieve with generative, fall back to BM25 if needed"""
        if self.retrieval_mode == "generative":
            try:
                facts = self._get_session_facts(session_id)
                relevant_facts, metrics = self.generative_retriever.search_facts(
                    query, facts, k=10
                )

                # Log query for volume tracking
                self._log_query_volume(session_id)

                return relevant_facts
            except Exception as e:
                # Fall back to BM25 on error
                return self.bm25_retriever.search(query, facts)
        else:
            return self.bm25_retriever.search(query, facts)
```

**Pros**:
- Fallback reliability
- Can A/B test both approaches
- Gradual migration path

**Cons**:
- More complex code
- Still need to maintain BM25

---

### Option 3: Adaptive (Switch based on query volume)

**Architecture**:
```python
class ANEService:
    def __init__(self, model_path: str):
        self.inference = ANEInference(model_path)
        self.generative_retriever = GenerativeRetriever(model_path)
        self.bm25_retriever = BM25Retriever()
        self.query_counter = QueryVolumeCounter()

    async def retrieve_facts(self, query: str, session_id: str) -> list[dict]:
        """Adaptively choose retrieval method based on volume"""
        # Check recent query volume
        queries_per_day = self.query_counter.get_rate(session_id)

        # Break-even: 137 queries/day for typical corpus
        if queries_per_day < 137:
            # Use generative (cheaper at low volume)
            return await self._generative_search(query, session_id)
        else:
            # Use BM25 (cheaper at high volume)
            return self._bm25_search(query, session_id)
```

**Pros**:
- Automatically optimizes for cost
- Best of both worlds
- Responds to usage patterns

**Cons**:
- Most complex
- Requires query volume tracking
- Switching logic complexity

---

## Recommended Approach

### Phase 1: Usage Analysis (Week 1)

**Goal**: Determine if we're in the <137 queries/day range

**Actions**:
1. Add query volume logging to current service
2. Run for 1 week across typical nanobot usage
3. Measure:
   - Queries per session per day
   - Query types (keyword vs semantic)
   - Corpus sizes at query time

**Decision criteria**:
```
If avg_queries_per_day < 137:
    → Proceed to Phase 2 (generative integration)
Else:
    → Keep BM25, document findings
```

### Phase 2: Generative Integration (Week 2)

**Goal**: Integrate generative retrieval as primary method

**Implementation**: Option 2 (Hybrid with fallback)

**Steps**:

1. **Create retrieval interface** (`retrieval.py`):
```python
class RetrievalInterface:
    """Abstract interface for fact retrieval"""

    def search_facts(self, query: str, facts: list[dict], k: int) -> list[dict]:
        raise NotImplementedError

class GenerativeRetrievalAdapter(RetrievalInterface):
    def __init__(self, model_path: str):
        self.retriever = GenerativeRetriever(model_path)

    def search_facts(self, query: str, facts: list[dict], k: int) -> list[dict]:
        results, metrics = self.retriever.search_facts(query, facts, k)
        return results

class BM25RetrievalAdapter(RetrievalInterface):
    def __init__(self):
        self.retriever = BM25Retriever()

    def search_facts(self, query: str, facts: list[dict], k: int) -> list[dict]:
        return self.retriever.search(query, facts, k)
```

2. **Update `service.py`**:
```python
class ANEService:
    def __init__(self, model_path: str, retrieval_mode: str = "generative"):
        self.inference = ANEInference(model_path)

        # Initialize retrievers
        if retrieval_mode == "generative":
            self.retriever = GenerativeRetrievalAdapter(model_path)
            self.fallback_retriever = BM25RetrievalAdapter()
        elif retrieval_mode == "bm25":
            self.retriever = BM25RetrievalAdapter()
            self.fallback_retriever = None
        else:
            raise ValueError(f"Unknown retrieval mode: {retrieval_mode}")

    async def retrieve_facts(self, query: str, session_id: str) -> list[dict]:
        """Retrieve relevant facts with fallback"""
        facts = self._get_session_facts(session_id)

        try:
            return self.retriever.search_facts(query, facts, k=10)
        except Exception as e:
            if self.fallback_retriever:
                logger.warning(f"Generative retrieval failed: {e}, falling back to BM25")
                return self.fallback_retriever.search_facts(query, facts, k=10)
            else:
                raise
```

3. **Add configuration** (`config.yaml`):
```yaml
retrieval:
  mode: generative  # or: bm25, adaptive
  fallback_enabled: true
  query_volume_tracking: true
  break_even_queries_per_day: 137
```

### Phase 3: A/B Testing (Week 3)

**Goal**: Validate quality improvement over BM25

**Method**:
1. Run parallel retrievals (generative + BM25) on same queries
2. Compare results:
   - Recall on paraphrased queries
   - Precision on keyword queries
   - User satisfaction (if measurable)
3. Measure:
   - Query latency distribution
   - Cost per query (tokens)
   - Failure rate

**Success criteria**:
- Generative recall ≥ BM25 recall on semantic queries
- Generative precision ≥ 0.7 on all query types
- Failure rate < 5%

### Phase 4: Production Deployment (Week 4)

**Goal**: Ship generative retrieval as default

**Actions**:
1. Update service to use generative by default
2. Keep BM25 as fallback (don't remove)
3. Monitor for 1 month:
   - Query success rate
   - Latency percentiles (p50, p95, p99)
   - Cost per session
4. Document in production:
   - Retrieval mode selection logic
   - Fallback behavior
   - Query volume tracking

---

## Cost Analysis

### Generative Retrieval Cost

At ANE's 36.2x cost ratio:
- **Per query**: 110 output tokens = 3,982 input token equivalents
- **Per day** (100 queries): 398,200 input token equivalents
- **Per month** (3000 queries): 11,946,000 input token equivalents

### BM25 Cost

- **Per query**: Free (CPU-only)
- **Index building**: ~960ms every 45 minutes (negligible)

### Break-Even Analysis

Using ARM E break-even formula:

| Corpus Size | Index Time | Break-Even Point | Generative Wins If |
|-------------|------------|------------------|-------------------|
| Small       | 0.32s      | 45 queries/day   | <45/day |
| **Medium**  | **0.96s**  | **137 queries/day** | **<137/day** |
| Large       | 1.92s      | 274 queries/day  | <274/day |

**Nanobot usage estimate**: ~20-50 queries/day per session (typical)
**Verdict**: Within generative-wins range

---

## Risk Mitigation

### Risk 1: Query volume exceeds break-even

**Mitigation**:
- Keep BM25 code in codebase
- Add query volume monitoring
- Implement adaptive switching (Option 3)

### Risk 2: Generative quality degrades on edge cases

**Mitigation**:
- Fallback to BM25 on error
- A/B testing during deployment
- User feedback collection

### Risk 3: 7s latency too slow

**Mitigation**:
- Run retrieval asynchronously in background
- Preload likely queries (predictive retrieval)
- Cache recent query results

### Risk 4: Model overload (retrieval + extraction + consolidation)

**Mitigation**:
- Use separate ANE model instance for retrieval
- Queue management for concurrent calls
- Fall back to BM25 if ANE busy

---

## Implementation Checklist

### Phase 1: Usage Analysis
- [ ] Add query volume logging to service.py
- [ ] Deploy logging for 1 week
- [ ] Analyze query patterns
- [ ] Calculate actual queries/day
- [ ] Decision: proceed or keep BM25

### Phase 2: Integration (if Phase 1 proceeds)
- [ ] Create `retrieval.py` with interface
- [ ] Implement GenerativeRetrievalAdapter
- [ ] Implement BM25RetrievalAdapter
- [ ] Update service.py with hybrid mode
- [ ] Add configuration support
- [ ] Unit tests for both adapters

### Phase 3: A/B Testing
- [ ] Run parallel retrievals
- [ ] Compare recall/precision
- [ ] Measure latency
- [ ] Collect failure cases
- [ ] Decision: deploy or iterate

### Phase 4: Deployment
- [ ] Set generative as default
- [ ] Keep BM25 fallback active
- [ ] Production monitoring
- [ ] Document behavior
- [ ] Performance tuning

---

## Success Metrics

### Quality Metrics
- **Recall@10**: ≥75% (ARM E baseline)
- **Precision@10**: ≥70%
- **Failure rate**: <5%

### Cost Metrics
- **Tokens per query**: ~110 (ARM E baseline)
- **Break-even**: <137 queries/day

### Operational Metrics
- **Latency p95**: <10s
- **Fallback rate**: <10%
- **Uptime**: >99%

---

## Alternative: Defer ARM E Integration

If usage analysis shows >137 queries/day:

**Decision**: Keep BM25, document why generative wasn't adopted

**Documentation**:
- Query volume exceeds break-even
- BM25 more cost-effective at current scale
- Revisit if:
  - Query volume drops below 137/day
  - ANE decode speed improves
  - Embedding approach fails (like AMD's)

---

## AMD NPU Context

AMD's investigation closed as NO-GO due to:
1. **Synchronous timing constraint** (300s vs 649-790s needed)
2. **Large corpus size** (40K tokens)

But they explicitly stated:
> "The only remaining avenue is architectural: redesign to run asynchronously
> in the background, the way the sibling Apple-ANE project (nanobot_ane) does
> it successfully."

**Our advantages**:
- ✅ Async architecture (we already have this!)
- ✅ Smaller corpus per session
- ✅ Faster decode (26.8 vs 14 tok/s)
- ✅ No global lock constraint

**Conclusion**: We can succeed where AMD couldn't because of architectural differences, not just hardware.

---

## Next Steps

**Immediate**:
1. Review this plan with stakeholders
2. Decide: proceed with Phase 1 usage analysis?
3. If yes: implement query volume logging (1-2 days)

**Week 1**:
- Deploy logging, collect data
- Analyze query patterns

**Week 2+**:
- If <137 queries/day: proceed to Phase 2
- If >137 queries/day: document and close

**References**:
- ARM E results: `arms/results/arm_e_retrieval_results.json`
- ARM E test: `arms/arm_e/test_generative_retrieval.py`
- Generative retriever: `arms/arm_e/generative_retriever.py`
- AMD NPU findings: `arms/CROSS_POLLINATION_AMD_NPU.md`
