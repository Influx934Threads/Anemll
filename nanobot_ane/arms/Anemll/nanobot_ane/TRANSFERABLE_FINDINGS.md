# Transferable Findings - Platform-Agnostic NPU Optimization Lessons

**Purpose**: Lessons learned from ANE investigation that apply to ANY NPU hardware (AMD, Apple, Google, etc.)
**Audience**: NPU optimization teams, ML engineers, researchers
**Date**: 2026-11-06
**Status**: ✅ **Validated configuration DEPLOYED to production on ANE** (2026-11-06 19:53 UTC)

---

## Core Principles

### 1. Budget Constraints Beat Complex Optimization

**Finding**: Tight token budget constraints (≤100 tokens) can achieve better results than complex chunking strategies.

**Evidence**:
- ANE 4B + Budget 100: 100% recall, ~42% savings
- ANE 4B + chunk4: 87-100% recall (inconsistent), ~39% savings
- Simpler configuration outperforms complex one

**Why This Works (Platform-Independent)**:
1. **Forced discipline**: Hard limits prevent model verbosity
2. **Predictable behavior**: Same constraint every call = consistent output
3. **Easier debugging**: Single knob to tune vs multi-parameter optimization
4. **Model agnostic**: Works across architectures (Qwen, likely Hermes, etc.)

**How to Apply to Your NPU**:
```python
# Template for any NPU/model
prompt = f"""Extract facts from this <unit>. Target ≤N tokens.
Be concise but clear. Abbreviate where unambiguous.
Preserve: <critical_content_types>.

<unit>:
{content}

Facts (≤N tokens):"""

# Start with N=100, tune up/down based on your use case
# Measure: recall quality vs token efficiency
```

**Key Variables to Test**:
- Budget size (80, 100, 120, 150 tokens)
- Budget scaling (per-turn vs per-chunk)
- Prompt wording (natural language vs structured)

---

### 2. Multi-Seed Validation is Non-Negotiable

**Finding**: Single-seed testing can give misleading results. Minimum 3 seeds required for production confidence.

**Evidence from ANE**:
- Seed 101: chunk4 showed 8.1% savings, 100% recall ✅
- Seed 202: chunk4 showed -1.8% savings, 87.5% recall ❌
- Seed 303: chunk4 showed -0.9% savings, 100% recall ⚠️
- **Conclusion**: chunk4 unreliable despite 1/3 success

**Why Single-Seed Fails (Universal)**:
1. **Conversation diversity**: Different patterns stress different model capabilities
2. **Lucky outliers**: One seed may hit model's sweet spot
3. **Statistical noise**: Small sample = high variance
4. **Production mismatch**: Real conversations won't match lucky seed

**Minimum Validation Protocol** (Apply to Any Platform):

```python
# Multi-seed validation template
seeds = [101, 202, 303]  # Minimum 3, ideally 5+
results = []

for seed in seeds:
    conversation = generate_synthetic(seed=seed, turns=48, facts=32)

    for config in configurations:
        extracted = run_extraction(conversation, config)
        recall = score_recall(extracted, conversation.planted_facts)
        tokens = count_tokens(extracted)

        results.append({
            'seed': seed,
            'config': config,
            'recall': recall,
            'tokens': tokens
        })

# Only deploy if ALL seeds pass threshold
success_rate = sum(r['recall'] == 1.0 for r in results) / len(results)
if success_rate < 1.0:
    print(f"FAIL: Only {success_rate:.0%} success rate - not production ready")
```

**Success Criteria** (Platform-Independent):
- **Perfect recall**: 100% across all seeds (if required by use case)
- **Consistent savings**: <10% variance across seeds
- **No catastrophic failures**: 0% seeds with <90% recall

---

### 3. Test Against True Unconstrained Baselines

**Finding**: Hidden constraints in "baseline" configurations can mask true optimization impact.

**ANE Example**:
- **Apparent baseline**: chunk1 (Budget 100) = 0% savings
- **True baseline**: No budget constraint = ~9000 tokens
- **Real Budget 100 savings**: ~42% (not 0%!)

**Why This Happens (Universal)**:
1. **Incremental testing**: Start with "good enough" config, iterate from there
2. **Implicit constraints**: Prompts include limits without realizing
3. **Missing comparison**: Never test truly unconstrained generation
4. **Anchoring bias**: First config becomes mental "baseline"

**How to Avoid** (Any Platform):

```python
# Always establish TRUE baseline first
configs = [
    "unconstrained",     # No limits - pure model behavior
    "baseline_prod",     # Current production config
    "optimization_v1",   # Your new optimization
    "optimization_v2",   # Alternative approach
]

# Measure everything from unconstrained
for config in configs:
    result = test(config)
    savings_vs_unconstrained = 1 - (result.tokens / unconstrained.tokens)
    savings_vs_baseline = 1 - (result.tokens / baseline.tokens)

    print(f"{config}:")
    print(f"  vs unconstrained: {savings_vs_unconstrained:.1%}")
    print(f"  vs baseline: {savings_vs_baseline:.1%}")
```

**Red Flags** (Platform-Agnostic):
- Baseline config has prompt constraints ("be concise", "target N tokens")
- Baseline config has max_tokens limit
- Never tested model without any limits
- Optimization shows small gains (<10%) vs baseline

---

### 4. Model Size Thresholds Exist for Every Task

**Finding**: There are quality thresholds below which models cannot reliably perform a task, regardless of prompt engineering.

**ANE Evidence**:
- **1.7B**: 90-97% recall (FAILS - misses 3-10% of facts)
- **4B**: 100% recall (PASSES - reliable performance)
- **9B**: 100% recall + better efficiency (EXCEEDS)

**Why Thresholds Exist (Universal)**:
1. **Capacity limits**: Small models lack reasoning power
2. **Non-linear improvements**: 2x params ≠ 2x quality
3. **Emergent abilities**: Some capabilities only appear at scale
4. **Context management**: Larger models track more simultaneously

**How to Find Your Threshold** (Any Platform/Task):

```python
# Test multiple model sizes on SAME task
models = ["1.7B", "4B", "7B", "9B", "13B"]  # Your available sizes
target_quality = 0.95  # Your minimum acceptable quality

results = {}
for model_size in models:
    quality, cost = benchmark(model_size, task)
    results[model_size] = {
        'quality': quality,
        'cost': cost,
        'cost_per_quality': cost / quality
    }

# Find minimum viable size
viable_models = [m for m, r in results.items() if r['quality'] >= target_quality]
optimal = min(viable_models, key=lambda m: results[m]['cost'])

print(f"Minimum viable: {viable_models[0]}")
print(f"Optimal (cost/quality): {optimal}")
```

**Key Insight** (Platform-Independent):
- Don't assume prompt engineering can fix model capacity limits
- Test smallest → largest to find minimum viable size
- Balance quality threshold vs resource cost
- Below threshold: No amount of optimization helps

---

### 5. Tighter Constraints Can Improve Quality (The Constraint Paradox)

**Finding**: Counterintuitively, tighter limits sometimes produce BETTER quality than loose limits or no limits.

**ANE Evidence**:

| Budget | Tokens | Recall | Observation |
|--------|--------|--------|-------------|
| None | ~9000 | 100% | Verbose but accurate |
| 150 | ~8100 | 87.5% | Too loose - model rambles, misses facts |
| **100** | **~5300** | **100%** | **Tight enough to force discipline** |

**Why This Happens** (Universal Mechanism):

1. **Forced prioritization**: Model must choose what's important
2. **Prevents rambling**: Can't waste tokens on elaboration
3. **Reduces noise**: Less room for irrelevant content
4. **Maintains focus**: Budget keeps model on task

**The Goldilocks Zone** (Platform-Agnostic):

```
Too loose (≥150)  → Model becomes verbose, quality degrades
Just right (100)  → Model forced to be surgical, quality maintained
Too tight (<80)   → Model truncates critical content, quality degrades
```

**How to Find Your Sweet Spot** (Any Platform):

```python
# Test budget sweep
budgets = [50, 80, 100, 120, 150, 200, None]
results = []

for budget in budgets:
    tokens, quality = test_budget(budget)
    results.append({
        'budget': budget,
        'tokens': tokens,
        'quality': quality,
        'efficiency': quality / tokens  # Quality per token
    })

# Find maximum efficiency while maintaining quality
optimal = max(
    [r for r in results if r['quality'] >= quality_threshold],
    key=lambda r: r['efficiency']
)

print(f"Optimal budget: {optimal['budget']} tokens")
print(f"Quality: {optimal['quality']:.1%}, Tokens: {optimal['tokens']}")
```

**Universal Principle**:
- Start with generous budget
- Tighten until quality starts to degrade
- Back off slightly from degradation point
- That's your sweet spot

---

### 6. Synthetic Conversations Enable Rigorous Testing

**Finding**: Generating synthetic conversations with planted facts enables precise recall measurement.

**ANE Methodology** (Transferable):

```python
# 1. Generate conversation with known facts
def generate_synthetic(seed, num_turns=48, num_facts=32):
    random.seed(seed)
    conversation = []
    planted_facts = []

    for turn in range(num_turns):
        # Mix technical discussion with planted facts
        user_msg = generate_user_message(turn)
        assistant_msg = generate_assistant_message(turn)

        # Plant fact as "aside" within turn
        if should_plant_fact(turn, num_facts):
            fact = generate_fact(turn)
            assistant_msg = insert_fact_as_aside(assistant_msg, fact)
            planted_facts.append(PlantedFact(fact, turn))

        conversation.append({'user': user_msg, 'assistant': assistant_msg})

    return conversation, planted_facts

# 2. Extract facts with your system
extracted = run_extraction(conversation)

# 3. Score recall precisely
recalled = [f for f in planted_facts if f.text in extracted]
recall = len(recalled) / len(planted_facts)

# 4. Identify what was missed
missed = [f for f in planted_facts if f not in recalled]
```

**Why This Works** (Universal):

1. **Ground truth**: You know exactly what should be extracted
2. **Reproducible**: Same seed = same conversation
3. **Diverse testing**: Different seeds test different patterns
4. **Precise metrics**: No ambiguity in success/failure
5. **Scalable**: Generate hundreds of test cases cheaply

**Adaptation for Your Platform**:

```python
# Platform-agnostic planted fact template
class PlantedFact:
    def __init__(self, fact_type, value, turn):
        self.type = fact_type  # file_path, version, decision, etc.
        self.value = value
        self.turn = turn
        self.text = self.render()

    def render(self):
        # Format fact as natural aside
        templates = {
            'file_path': f"Working with {self.value}",
            'version': f"Using version {self.value}",
            'decision': f"User {self.value}",
            'error': f"Encountered: {self.value}"
        }
        return templates[self.type]

# Plant facts across conversation
fact_types = ['file_path', 'version', 'decision', 'error']
planted = []
for i in range(32):  # Plant 32 facts
    fact_type = random.choice(fact_types)
    fact = generate_fact(fact_type)
    turn = select_turn_for_planting(i)
    planted.append(PlantedFact(fact_type, fact, turn))
```

**Key Benefits** (Platform-Independent):
- Tests real-world messiness (facts buried in code/logs/discussion)
- Quantifiable quality metrics (not subjective)
- Cheap to generate (vs manual annotation)
- Reproducible across teams/platforms

---

### 7. Natural Language Prompts Beat Structured Formats

**Finding**: Simple natural language prompts can outperform structured formats (JSON, XML, tags) for NPU workloads.

**ANE Evidence**:
- **Natural language Budget 100**: 100% recall, ~42% savings ✅
- **Structured formats** (JSON, tags): 19-30% hallucinations ❌

**Why Structured Formats Fail on NPUs** (Hypothesis):

1. **Training data bias**: Less structured format examples in training
2. **Token overhead**: JSON braces/quotes waste budget
3. **Parsing fragility**: Small errors break entire output
4. **NPU specifics**: May amplify certain failure modes

**Natural Language Template** (Universal):

```python
# Simple, effective prompt structure
prompt = f"""<Task description>. Target ≤N tokens.
<Quality guidelines>.
Preserve: <critical content types>.

<Input label>:
{content}

<Output label> (≤N tokens):"""
```

**vs Structured Format** (Often Worse):

```python
# Avoid unless proven better for YOUR use case
prompt = f"""Extract facts as JSON array.
{{
  "facts": [
    {{"type": "...", "value": "...", "turn": N}},
    ...
  ]
}}

Input:
{content}

Output:"""
```

**Testing Protocol** (Platform-Agnostic):

```python
# Always A/B test natural vs structured
formats = {
    'natural': natural_language_prompt,
    'json': json_format_prompt,
    'xml': xml_format_prompt,
    'tagged': tagged_format_prompt
}

for format_name, prompt_template in formats.items():
    hallucinations = test_hallucination_rate(prompt_template)
    recall = test_recall(prompt_template)
    parseability = test_output_parsing(prompt_template)

    print(f"{format_name}:")
    print(f"  Hallucinations: {hallucinations:.1%}")
    print(f"  Recall: {recall:.1%}")
    print(f"  Parse success: {parseability:.1%}")

# Use natural language unless structured proves clearly better
```

---

### 8. Mechanical Merge Beats LLM Consolidation

**Finding**: Zero-LLM mechanical merging at CPU level outperforms LLM-based consolidation.

**Cross-Platform Evidence**:
- **AMD NPU**: LLM reduce "never beat 5/8 recall", non-monotonic
- **ANE**: Mechanical merge 3,725x faster, 93% vs 50% recall

**Why LLM Consolidation Fails** (Universal):

1. **Non-monotonicity**: Better input → worse output (unpredictable)
2. **Second pass cost**: Doubles inference time on constrained hardware
3. **Error accumulation**: Mistakes in extraction + mistakes in consolidation
4. **Context limitations**: Can't see full conversation during reduce

**Mechanical Merge Algorithm** (Platform-Agnostic):

```python
def mechanical_merge(extracted_facts: List[str]) -> str:
    """
    Zero-LLM fact consolidation.
    Works on ANY platform - pure CPU operation.
    """
    # 1. Deduplicate
    unique_facts = set()
    for fact in extracted_facts:
        normalized = normalize(fact)  # lowercase, strip, etc.
        if not is_duplicate(normalized, unique_facts):
            unique_facts.add(fact)

    # 2. Simple concatenation (or light formatting)
    consolidated = "\n".join(sorted(unique_facts))

    return consolidated

def is_duplicate(fact: str, existing: Set[str]) -> bool:
    """Simple similarity check - tune for your use case"""
    fact_normalized = fact.lower().strip()

    for existing_fact in existing:
        existing_normalized = existing_fact.lower().strip()

        # Exact match
        if fact_normalized == existing_normalized:
            return True

        # High overlap (>80% shared words)
        overlap = jaccard_similarity(fact_normalized, existing_normalized)
        if overlap > 0.8:
            return True

    return False
```

**Benefits** (Universal):
- **Fast**: CPU operations (milliseconds vs seconds)
- **Predictable**: Deterministic behavior
- **Cheap**: No second LLM call
- **Reliable**: No hallucinations or degradation
- **Platform-agnostic**: Works on any NPU/GPU/CPU

---

## Summary: Universal Optimization Principles

### Do This on ANY NPU:

1. ✅ **Use tight budget constraints** (≤100 tokens) - simpler and effective
2. ✅ **Multi-seed validation** (minimum 3) - catch inconsistencies early
3. ✅ **Test vs unconstrained baseline** - measure true optimization impact
4. ✅ **Find model size threshold** - don't fight capacity limits
5. ✅ **Use synthetic conversations** - rigorous, reproducible testing
6. ✅ **Prefer natural language** - avoid structured formats unless proven better
7. ✅ **Mechanical merge** - skip LLM consolidation

### Avoid This:

1. ❌ **Single-seed validation** - misleading results
2. ❌ **Complex optimization first** - start simple (budgets)
3. ❌ **Assuming bigger budgets = better** - test the constraint paradox
4. ❌ **Structured output formats** - hallucination risk
5. ❌ **LLM consolidation** - mechanical merge is faster/better
6. ❌ **Under-sized models** - find your quality threshold

---

## Replication Guide

To replicate our findings on YOUR platform:

1. **Choose model size** - Test 4B, 7B, 9B (find threshold)
2. **Generate synthetic data** - 3+ seeds, 48 turns, 32 planted facts
3. **Test budget variants** - 80, 100, 120, 150, None
4. **Measure precisely** - Recall (planted facts found), tokens (output size)
5. **Validate multi-seed** - All 3 seeds must pass quality threshold
6. **Deploy simplest winner** - Prefer simple configs over complex

**Questions for cross-platform comparison?**
- Share your results - we're interested in divergences
- Compare findings - validate or contradict our observations
- Build knowledge base - help entire NPU community

---

## Contact & Collaboration

These findings are shared openly for NPU community benefit. If you:

- Replicate on different platform (AMD, Google, etc.)
- Find contradictory results
- Discover new transferable principles
- Want to collaborate on testing

Please contribute back! Cross-platform validation benefits everyone.

**Repository**: AneMLL/nanobot_ane
**Documentation**: See `arms/README.md` for investigation details
**Methodology**: See `arms/arm_d/BUDGET_100_VALIDATION.md` for test protocols
