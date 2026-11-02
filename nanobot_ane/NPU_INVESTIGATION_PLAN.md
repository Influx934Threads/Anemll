# NPU Best-Fit Envelope Investigation Plan for nanobot_ane

**Inspired by:** AMD XDNA2 NPU investigation findings (NPU-BEST-FIT-ENVELOPE.md)

**Goal:** Characterize Apple ANE's performance envelope and apply validated optimization strategies from the AMD investigation.

## Investigation Structure

Each ARM is a separate experiment that:
1. Has its own test harness (`test_arm_X.py`)
2. Produces measurable results (`results_arm_X.json`)
3. Can reuse code from previous arms
4. Runs independently (can be executed in parallel)

**Shared Infrastructure:**
- `arms/shared/metrics.py` - Common measurement utilities
- `arms/shared/fixtures.py` - Test data (conversations, turns, facts)
- `arms/results/` - JSON results for each arm

---

## ARM A: ANE Characteristics Profiling

**Question:** Does Apple ANE show similar cost asymmetry to AMD NPU's 39x ratio (prefill ~550 tok/s, decode ~14 tok/s)?

**Hypothesis:** ANE will show prefill advantage over decode, but ratio may differ from AMD's 39x.

### Test Matrix

| Input Size | Output Size | Iterations | Metric |
|------------|-------------|------------|--------|
| 512 tokens | 10, 50, 100, 200, 500 tokens | 10 | Prefill time, decode time, total time |
| 1024 tokens | 10, 50, 100, 200, 500 tokens | 10 | Prefill time, decode time, total time |
| 2048 tokens | 10, 50, 100, 200, 500 tokens | 10 | Prefill time, decode time, total time |
| 4096 tokens | 10, 50, 100, 200, 500 tokens | 10 | Prefill time, decode time, total time |
| 8192 tokens | 10, 50, 100, 200, 500 tokens | 5 | Prefill time, decode time, total time |

### Deliverables

1. **`arms/arm_a/test_ane_profile.py`** - Test harness
2. **`arms/arm_a/profiler.py`** - Instrumented ANE inference
3. **`arms/arm_a/analyze_results.py`** - Calculate ratios and find envelope
4. **`arms/results/arm_a_profile.json`** - Raw measurements
5. **`arms/results/arm_a_analysis.md`** - Human-readable findings

### Success Criteria

- Measured prefill/decode ratio with <5% variance
- Identified ANE's "best-fit envelope" (max reliable input/output)
- Wall-clock time prediction formula accurate to within 5%

### Code Dependencies

- Reuses: `ane_inference.py` (instrumented with timing)
- New: Profiler wrapper that separates prefill/decode timing

---

## ARM B: Generative Selection (Extractive ID Emission)

**Question:** Can generative ID selection beat LLM fact extraction for turn ranking when cost is measured in output tokens?

**Hypothesis:** Emitting turn IDs (~30 tokens) will be cheaper and more accurate than extracting facts (~100-150 tokens per turn).

### Test Scenarios

**Scenario 1: Turn Ranking**
- Input: 100 turns (conversation history)
- Task: "Which 10 turns are most relevant to [query]?"
- Baseline: Current fact extraction + semantic matching
- Test: Generative selector emitting turn IDs

**Scenario 2: Fact Retrieval**
- Input: 200 facts from session
- Task: "Which facts relate to [user preference]?"
- Baseline: Full fact list scan
- Test: Generative selector emitting fact IDs

### Deliverables

1. **`arms/arm_b/test_generative_selection.py`** - Test harness
2. **`arms/arm_b/selector.py`** - Generative ID selector implementation
3. **`arms/arm_b/baseline_ranker.py`** - BM25/TF-IDF classical ranker for comparison
4. **`arms/arm_b/fixtures.py`** - Ground truth datasets with labeled relevance
5. **`arms/results/arm_b_selection.json`** - Recall@k, cost in output tokens
6. **`arms/results/arm_b_analysis.md`** - Precision/recall curves, cost comparison

### Prompts

**Generative Selector Prompt:**
```
Given this conversation history with turn IDs, emit ONLY the IDs of turns
relevant to the query. Respond with a JSON array of integers, nothing else.

Query: {query}

Turns:
[1] User: "Set the timeout to 30 seconds"
    Assistant: "I've configured the timeout to 30 seconds."
[2] User: "What's the weather like?"
    Assistant: "I don't have access to weather data."
...

Emit turn IDs as JSON: [1, 5, 12]
```

### Success Criteria

- Recall@10 >= current fact extraction baseline
- Output tokens < 50 (vs 100-150 for fact extraction)
- Cost flat in input size (test at 50, 100, 200 turns)

### Code Dependencies

- Reuses: `ane_inference.py`, `arms/shared/metrics.py`
- New: Selector prompt engineering, classical ranker baseline

---

## ARM C: Map-Mechanical-Merge Pattern

**Question:** Can we eliminate the re-consolidation LLM pass (every 5 turns) with mechanical merging?

**Hypothesis:** CPU-side deduplication + fact grouping can replace the LLM "merge facts into coherent summary" step, avoiding multi-pass abstraction.

### Current Architecture (Baseline)

```
Turn 1 → Extract facts (LLM, ~5s) → facts_list = [f1, f2, f3]
Turn 2 → Extract facts (LLM, ~5s) → facts_list = [f1, f2, f3, f4, f5]
...
Turn 5 → Extract facts (LLM, ~5s) → facts_list = [f1...f12]
      → Re-consolidate (LLM, ~10s) → "User prefers X. System uses Y."
```

**Cost:** 5 extractions (5s each) + 1 consolidation (10s) = **35s per 5 turns**

### Map-Mechanical-Merge Architecture (Test)

```
Turn 1 → Extract structured facts (LLM, JSON) → [{type, content, entities}]
Turn 2 → Extract structured facts (LLM, JSON) → [{type, content, entities}]
...
Turn 5 → CPU merge:
         - Group by fact type
         - Deduplicate by entity/content similarity
         - Format into sections (no LLM)
```

**Cost:** 5 extractions (5s each) + CPU merge (<1s) = **26s per 5 turns**

### Test Matrix

| Turns | Current (LLM consolidation) | Map-Mechanical | Metric |
|-------|----------------------------|----------------|--------|
| 5 turns | Extract + consolidate | Extract + CPU merge | Time, recall, duplicate count |
| 10 turns | 2x consolidation cycles | Extract + CPU merge | Time, recall, duplicate count |
| 20 turns | 4x consolidation cycles | Extract + CPU merge | Time, recall, duplicate count |

### Deliverables

1. **`arms/arm_c/test_map_merge.py`** - Test harness comparing both approaches
2. **`arms/arm_c/mechanical_merger.py`** - CPU-side fact merging logic
3. **`arms/arm_c/structured_extractor.py`** - Enhanced fact extraction with entity tagging
4. **`arms/arm_c/deduplicator.py`** - Similarity-based deduplication (fuzzy string matching)
5. **`arms/results/arm_c_merge.json`** - Time, token, recall comparison
6. **`arms/results/arm_c_analysis.md`** - Quality assessment (human eval)

### Mechanical Merge Algorithm

```python
def mechanical_merge(facts: list[dict]) -> dict:
    """
    Zero-LLM merge using grouping + deduplication
    """
    # 1. Group by fact type
    grouped = defaultdict(list)
    for fact in facts:
        grouped[fact['type']].append(fact)

    # 2. Deduplicate within each group
    deduped = {}
    for fact_type, fact_list in grouped.items():
        deduped[fact_type] = deduplicate_facts(fact_list)

    # 3. Format into sections
    sections = {}
    for fact_type, unique_facts in deduped.items():
        sections[fact_type] = format_section(unique_facts)

    return {
        'text': '\n\n'.join(f"**{k}:**\n{v}" for k, v in sections.items()),
        'facts': [f for facts in deduped.values() for f in facts],
        'duplicate_count': len(facts) - sum(len(f) for f in deduped.values())
    }

def deduplicate_facts(facts: list[dict]) -> list[dict]:
    """
    Fuzzy deduplication based on content similarity
    """
    unique = []
    for fact in facts:
        if not any(similarity(fact['content'], u['content']) > 0.85 for u in unique):
            unique.append(fact)
    return unique
```

### Success Criteria

- Recall >= 95% of current LLM consolidation baseline
- Time savings >= 25%
- Output tokens reduced (no consolidation prompt overhead)
- Duplicate count within 10% of LLM baseline

### Code Dependencies

- Reuses: `ane_inference.py`, `service.py` fact extraction
- New: Mechanical merger, fuzzy deduplication (difflib or rapidfuzz)

---

## ARM D: Output-Token Budgeting and Optimization

**Question:** If we optimize for tokens *emitted* rather than tokens *processed*, how much can we save?

**Hypothesis:** Current prompts are not token-budget-aware; explicit output constraints will reduce cost without hurting quality.

### Current Prompts Analysis

**Fact Extraction Prompt** (from service.py):
- Current output: ~100-150 tokens per turn
- No explicit token budget

**Consolidation Prompt:**
- Target: "under 75 words" (~100 tokens)
- Actual: Often exceeds target

### Test Configurations

| Config | Prompt Strategy | Budget Constraint | Expected Output |
|--------|----------------|-------------------|-----------------|
| Baseline | Current prompts | None | ~100-150 tokens |
| D1_strict | "Emit ≤50 tokens" | Hard limit | ~50 tokens |
| D2_json | "JSON facts only, no prose" | Implicit (structure) | ~60 tokens |
| D3_ids | "Emit entity IDs, not full text" | Implicit (compression) | ~30 tokens |
| D4_sections | "Tagged facts: {type}:{content}" | Implicit (format) | ~70 tokens |

### Deliverables

1. **`arms/arm_d/test_token_budget.py`** - Test harness comparing prompts
2. **`arms/arm_d/prompt_variants.py`** - 5 prompt configurations
3. **`arms/arm_d/token_counter.py`** - Accurate token counting (tiktoken)
4. **`arms/arm_d/validator.py`** - Output quality checks (fact coverage, hallucination)
5. **`arms/results/arm_d_budget.json`** - Token counts, quality scores
6. **`arms/results/arm_d_prompts.md`** - Winning prompt configurations

### Prompt Examples

**D1_strict (Hard Budget):**
```
Extract facts from this conversation turn. Respond with ≤50 tokens.
Use extreme concision. Omit articles, use abbreviations.

Turn: {turn_text}

Facts (≤50 tokens):
```

**D2_json (Structured):**
```
Extract facts as JSON array. Each fact: {"t": "type", "c": "content"}.
Types: req, cfg, thresh, pref. Be concise.

Turn: {turn_text}

JSON:
```

**D3_ids (Entity Compression):**
```
Extract entities and assign IDs. Respond with ID mapping only.

Turn: {turn_text}

Entities:
1: timeout=30s
2: user_prefers_concise_mode
```

### Success Criteria

- Token reduction >= 40% vs baseline
- Fact coverage >= 90% (automated eval)
- Hallucination rate <= 5%
- One prompt config becomes new default

### Code Dependencies

- Reuses: `ane_inference.py`, `service.py`
- New: Token counter (tiktoken), quality validator

---

## ARM E: Generative Selection as Primary Retrieval (Bonus)

**Question:** Should we replace embeddings entirely with generative selection for `sb-search` equivalent?

**Hypothesis:** On ANE, generative selection (30 tokens out) beats embedding search (continuous reindexing cost).

### Comparison Setup

**Embedding Path (Hypothetical):**
- Index build: Embed all turns/facts every 45 min
- Query: Embed query, cosine similarity search
- Cost: Continuous (index rebuild) + per query (embed query)

**Generative Path:**
- Index build: None (work at query time)
- Query: LLM selects relevant turn/fact IDs
- Cost: Per query only (~30 tokens emitted)

### Test Scenarios

1. **sb-search queries** (if we had embedding baseline)
2. **Conversation search:** "Find turns about timeout configuration"
3. **Fact search:** "What are user preferences?"

### Deliverables

1. **`arms/arm_e/test_generative_retrieval.py`** - Query benchmark
2. **`arms/arm_e/generative_retriever.py`** - Query-time generative selector
3. **`arms/arm_e/cost_model.py`** - Break-even analysis (queries/day)
4. **`arms/results/arm_e_retrieval.json`** - Recall, latency, cost
5. **`arms/results/arm_e_cost_analysis.md`** - When generative beats embeddings

### Success Criteria

- Recall >= 80% on real queries
- Cost break-even point identified (e.g., <100 queries/day)
- Latency acceptable (<5s per query)

### Code Dependencies

- Reuses: ARM B selector code
- New: Cost modeling, retrieval interface

---

## Shared Infrastructure

### `arms/shared/metrics.py`

```python
from dataclasses import dataclass
from typing import Any
import time
import tiktoken

@dataclass
class InferenceMetrics:
    """Granular timing and token metrics"""
    prefill_time_ms: float
    decode_time_ms: float
    total_time_ms: float
    input_tokens: int
    output_tokens: int

    @property
    def prefill_tok_per_sec(self) -> float:
        return (self.input_tokens / self.prefill_time_ms) * 1000

    @property
    def decode_tok_per_sec(self) -> float:
        return (self.output_tokens / self.decode_time_ms) * 1000

    @property
    def cost_ratio(self) -> float:
        """Output token cost relative to input token"""
        if self.prefill_tok_per_sec == 0:
            return 0
        return self.prefill_tok_per_sec / self.decode_tok_per_sec

@dataclass
class QualityMetrics:
    """Recall, precision, F1 for evaluation"""
    true_positives: int
    false_positives: int
    false_negatives: int

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

class TokenCounter:
    """Accurate token counting using tiktoken"""
    def __init__(self, model_name: str = "gpt-3.5-turbo"):
        self.encoder = tiktoken.encoding_for_model(model_name)

    def count(self, text: str) -> int:
        return len(self.encoder.encode(text))

class TimingContext:
    """Context manager for precise timing"""
    def __init__(self, label: str = ""):
        self.label = label
        self.start_time = None
        self.elapsed_ms = None

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.elapsed_ms = (time.perf_counter() - self.start_time) * 1000

def measure_inference(fn, input_text: str, max_tokens: int) -> InferenceMetrics:
    """Measure prefill and decode separately"""
    counter = TokenCounter()
    input_tokens = counter.count(input_text)

    with TimingContext("prefill") as prefill:
        # Simulate prefill (actual impl hooks into ANE)
        pass

    with TimingContext("decode") as decode:
        output = fn(input_text, max_tokens=max_tokens)

    output_tokens = counter.count(output)

    return InferenceMetrics(
        prefill_time_ms=prefill.elapsed_ms,
        decode_time_ms=decode.elapsed_ms,
        total_time_ms=prefill.elapsed_ms + decode.elapsed_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens
    )
```

### `arms/shared/fixtures.py`

```python
"""Test data for all arms"""
from pathlib import Path
import json

class Fixtures:
    """Shared test data"""

    @staticmethod
    def get_conversation(size: str = "medium") -> list[dict]:
        """
        Get test conversation
        - small: 10 turns, ~2K tokens
        - medium: 50 turns, ~8K tokens
        - large: 100 turns, ~16K tokens
        """
        # Load from JSON files in arms/shared/fixtures/
        path = Path(__file__).parent / "fixtures" / f"conversation_{size}.json"
        return json.loads(path.read_text())

    @staticmethod
    def get_facts(count: int = 50) -> list[dict]:
        """Get test facts with ground truth labels"""
        path = Path(__file__).parent / "fixtures" / "facts_labeled.json"
        facts = json.loads(path.read_text())
        return facts[:count]

    @staticmethod
    def get_queries() -> list[dict]:
        """Get test queries with ground truth relevant turn IDs"""
        # Format: [{"query": "...", "relevant_turns": [1, 5, 12]}, ...]
        path = Path(__file__).parent / "fixtures" / "queries_labeled.json"
        return json.loads(path.read_text())
```

---

## Execution Plan

### Phase 1: Infrastructure (Day 1)
1. Create directory structure: `arms/arm_{a,b,c,d,e}/`
2. Implement shared metrics and fixtures
3. Generate test data (conversations, labeled queries)

### Phase 2: ARM A - Profile ANE (Day 2)
1. Write profiling harness
2. Run test matrix (5-10 hours on ANE)
3. Analyze results, determine cost ratio
4. Document ANE's best-fit envelope

### Phase 3: ARM B - Generative Selection (Day 3)
1. Implement selector prompts
2. Implement classical ranker baseline
3. Run comparison tests
4. Determine if generative selection wins

### Phase 4: ARM C - Map-Mechanical-Merge (Day 4)
1. Implement mechanical merger
2. Implement fuzzy deduplication
3. Run side-by-side comparison with current consolidation
4. Evaluate recall and time savings

### Phase 5: ARM D - Token Budgeting (Day 5)
1. Design 5 prompt variants
2. Implement token counter and validator
3. Run token budget tests
4. Select winning prompt(s)

### Phase 6: ARM E - Generative Retrieval (Optional, Day 6)
1. Implement generative retriever
2. Cost modeling
3. Determine break-even point

### Phase 7: Integration (Day 7)
1. Integrate winning arms into `service.py`
2. Update prompts in `NANOBOT_ANE_PROMPTS.md`
3. Add new metrics endpoints
4. Update documentation

---

## Success Metrics (Overall)

| Metric | Current | Target |
|--------|---------|--------|
| Compression time (per turn) | ~15s | <10s |
| Output tokens (per turn) | ~100-150 | <60 |
| Token cost ratio (output/input) | Unknown | Measured |
| Recall (fact coverage) | Unknown | >=90% |
| Duplicate reduction | Unknown | >=95% |

---

## Results Format

Each ARM produces:
1. **JSON results** (`arms/results/arm_X_results.json`)
2. **Analysis markdown** (`arms/results/arm_X_analysis.md`)
3. **Code artifacts** (`arms/arm_X/*.py`)

**Final deliverable:** `arms/results/INTEGRATION_RECOMMENDATION.md` - Which arms to integrate and how.

---

## Risk Mitigation

1. **ANE thermal throttling** (from AMD doc): Add temperature monitoring
2. **Burst faults** (from AMD doc): Add output validation, retry logic
3. **Generational loss** (from AMD doc): Verify mechanical merge doesn't degrade over time
4. **Test data bias**: Use real nanobot sessions, not synthetic data

---

## References

- **AMD NPU Investigation:** `~/Build/NPU-BEST-FIT-ENVELOPE.md`
- **Current nanobot_ane:** `/Users/agundez/Build/Anemll/nanobot_ane/`
- **Prompts:** `NANOBOT_ANE_PROMPTS.md`
- **Architecture:** `MEMORY_ARCHITECTURE.md`
