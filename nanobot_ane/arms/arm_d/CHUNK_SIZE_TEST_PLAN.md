# Chunk-Size Optimization Test Plan

**Date**: 2026-11-05
**Status**: Planning phase
**Priority**: HIGH (AMD NPU found 59-71% token reduction)

---

## Motivation

AMD NPU investigation found that **chunk size was the ONLY lever that provided real token reduction without prompt engineering**:

- 24 exchanges/chunk (baseline): 8,605 tokens
- **48 exchanges/chunk**: **3,568 tokens** (59% reduction, 8/8 recall on seed 101)
- BUT: Multi-seed confirmation showed 70.8% mean recall (not 100%)
- 9B model + chunk32 + cue: **8/8 recall, 3/3 seeds** (clean GO)

**Mechanism**: Fewer, larger chunks amortize per-call overhead (heading boilerplate, instruction tokens).

---

## Current nanobot Architecture

**Per-Turn Extraction**:
- Extract facts from EACH conversation turn (1 user + 1 assistant message)
- Each extraction pays fixed overhead
- For 100-turn conversation: 100 extraction calls

**Question**: Would extracting over N-turn windows reduce total tokens while preserving recall?

---

## Test Approach: Synthetic Fixtures

AMD used deterministic, seeded debugging transcripts with planted "needle" facts:

```python
def fixture_turns(target_tokens: int, seed: int):
    """Create synthetic conversation with known facts"""
    # Creates User/Assistant pairs
    # Plants specific facts to test recall
    # Returns: (turns, planted_facts, full_text)
```

**Why synthetic**:
1. Deterministic - same input every test
2. Known ground truth - we know exactly what facts should be extracted
3. Reproducible - multiple seeds for confirmation
4. No user interaction needed - can test automatically

---

## Implementation Plan

### Step 1: Create Synthetic Nanobot Conversations

**File**: `arms/arm_d/synthetic_fixtures.py`

```python
"""Synthetic nanobot conversations with planted facts"""

import random
from dataclasses import dataclass


@dataclass
class PlantedFact:
    """A fact we intentionally plant to test recall"""
    category: str  # 'file_path', 'config', 'error', 'decision', etc.
    text: str
    turn_index: int


def generate_nanobot_conversation(
    num_turns: int,
    seed: int,
    facts_per_10_turns: int = 8
) -> tuple[list[dict], list[PlantedFact]]:
    """
    Generate synthetic nanobot conversation with planted facts

    Returns:
        (turns, planted_facts)

    turns format:
        [{'user': '...', 'assistant': '...'}, ...]

    planted_facts format:
        [PlantedFact(...), ...]
    """
    random.seed(seed)

    turns = []
    planted = []

    # Templates for realistic nanobot exchanges
    templates = {
        'coding': [
            ("Help me debug this error: {error}",
             "Let me analyze that error. {explanation}"),
            ("Write a function to {task}",
             "Here's the implementation: {code}"),
        ],
        'configuration': [
            ("Set {config_key} to {config_value}",
             "Configuration updated: {config_key}={config_value}"),
            ("Check the {service} configuration",
             "Current {service} config: {details}"),
        ],
        'file_ops': [
            ("Create file at {filepath}",
             "Created {filepath} successfully"),
            ("Read {filepath}",
             "Contents of {filepath}: {content}"),
        ],
    }

    # Plant facts at specific intervals
    num_facts = (num_turns // 10) * facts_per_10_turns
    fact_positions = sorted(random.sample(range(num_turns), num_facts))

    fact_templates = [
        ('file_path', '/usr/local/bin/nanobot_{seed}'),
        ('config', 'timeout={value}s'),
        ('error', 'connection refused (errno {errno})'),
        ('model', 'model: qwen3-{size}b-v{version}'),
        ('decision', 'user chose option {option}'),
        ('measurement', 'latency: {latency}ms'),
        ('status', 'build status: {status}'),
        ('version', 'version {major}.{minor}.{patch}'),
    ]

    for i in range(num_turns):
        # Pick template category
        category = random.choice(list(templates.keys()))
        user_template, assistant_template = random.choice(templates[category])

        # Fill template
        if i in fact_positions:
            # Plant a specific fact
            fact_category, fact_template = random.choice(fact_templates)
            fact_text = fact_template.format(
                seed=seed,
                value=random.randint(10, 60),
                errno=random.randint(10, 99),
                size=random.choice(['1.7', '3', '8']),
                version=f"{random.randint(1,3)}.{random.randint(0,9)}",
                option=random.choice(['A', 'B', 'C']),
                latency=random.randint(100, 2000),
                status=random.choice(['passed', 'failed', 'pending']),
                major=random.randint(1, 3),
                minor=random.randint(0, 9),
                patch=random.randint(0, 20),
            )

            # Inject fact into assistant response
            user = user_template.format(
                error=f"Error {random.randint(100, 999)}",
                task="process data",
                config_key="timeout",
                config_value="30",
                service="api",
                filepath=f"/tmp/file_{i}.txt",
            )

            assistant = assistant_template.format(
                explanation=f"The issue is related to {fact_text}.",
                code="def process(): pass",
                config_key="timeout",
                config_value="30",
                service="api",
                details=f"Including {fact_text}",
                filepath=f"/tmp/file_{i}.txt",
                content="sample content",
            )

            planted.append(PlantedFact(
                category=fact_category,
                text=fact_text,
                turn_index=i
            ))
        else:
            # Regular turn without planted fact
            user = user_template.format(
                error=f"Error {random.randint(100, 999)}",
                task="process data",
                config_key="setting",
                config_value="value",
                service="system",
                filepath=f"/tmp/file_{i}.txt",
            )

            assistant = assistant_template.format(
                explanation="Standard response.",
                code="def helper(): pass",
                config_key="setting",
                config_value="value",
                service="system",
                details="Details here",
                filepath=f"/tmp/file_{i}.txt",
                content="content",
            )

        turns.append({
            'user': user,
            'assistant': assistant
        })

    return turns, planted


def score_recall(extracted_facts: str, planted: list[PlantedFact]) -> tuple[list, list]:
    """
    Score how many planted facts were recalled in extraction

    Returns:
        (recalled, missed)
    """
    recalled = []
    missed = []

    for fact in planted:
        # Simple substring match (could be more sophisticated)
        if fact.text in extracted_facts:
            recalled.append(fact)
        else:
            missed.append(fact)

    return recalled, missed
```

### Step 2: Test Chunk-Size Variants

**File**: `arms/arm_d/test_chunk_size.py`

```python
#!/usr/bin/env python3
"""
Test chunk-size optimization on synthetic nanobot conversations.

Based on AMD NPU finding: fewer, larger chunks amortize per-call overhead,
reducing total tokens by 59-71% with preserved recall (on 9B model + cue).
"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ane_inference import ANEInference
from arms.shared import TokenCounter
from arms.arm_d.synthetic_fixtures import (
    generate_nanobot_conversation,
    score_recall,
    PlantedFact
)


class ChunkSizeExtractor:
    """Extract facts with different chunk sizes"""

    def __init__(self, model_path: str):
        self.inference = ANEInference(model_path)
        self.token_counter = TokenCounter()

    def extract_per_turn(self, turns: list[dict]) -> tuple[str, dict]:
        """Baseline: extract per turn (chunk_size=1)"""
        all_facts = []
        total_tokens = 0

        for turn in turns:
            turn_text = f"User: {turn['user']}\nAssistant: {turn['assistant']}"

            prompt = f"""Extract facts from this conversation turn. Target ≤100 tokens.
Be concise but clear. Abbreviate where unambiguous.
Preserve: numbers, percentages, file paths, specific names, measurements.

Turn:
{turn_text}

Facts (≤100 tokens):"""

            output = asyncio.run(self.inference.generate(
                prompt=prompt,
                max_tokens=120,
                temperature=0.0
            ))

            all_facts.append(output)
            total_tokens += self.token_counter.count(output)

        return '\n\n'.join(all_facts), {
            'chunk_size': 1,
            'num_chunks': len(turns),
            'total_tokens': total_tokens,
            'avg_per_chunk': total_tokens / len(turns)
        }

    def extract_chunked(
        self,
        turns: list[dict],
        chunk_size: int
    ) -> tuple[str, dict]:
        """Extract over N-turn windows"""
        all_facts = []
        total_tokens = 0
        num_chunks = 0

        for i in range(0, len(turns), chunk_size):
            chunk_turns = turns[i:i+chunk_size]

            # Combine turns in chunk
            chunk_text = []
            for j, turn in enumerate(chunk_turns):
                chunk_text.append(f"Turn {i+j+1}:")
                chunk_text.append(f"User: {turn['user']}")
                chunk_text.append(f"Assistant: {turn['assistant']}")
                chunk_text.append("")

            combined_text = '\n'.join(chunk_text)

            prompt = f"""Extract facts from these {len(chunk_turns)} conversation turns. Target ≤{100 * len(chunk_turns)} tokens.
Be concise but clear. Abbreviate where unambiguous.
Preserve: numbers, percentages, file paths, specific names, measurements.

Turns:
{combined_text}

Facts (≤{100 * len(chunk_turns)} tokens):"""

            output = asyncio.run(self.inference.generate(
                prompt=prompt,
                max_tokens=120 * len(chunk_turns),
                temperature=0.0
            ))

            all_facts.append(output)
            total_tokens += self.token_counter.count(output)
            num_chunks += 1

        return '\n\n'.join(all_facts), {
            'chunk_size': chunk_size,
            'num_chunks': num_chunks,
            'total_tokens': total_tokens,
            'avg_per_chunk': total_tokens / num_chunks
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Test chunk-size optimization on synthetic conversations"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="/Users/agundez/Build/Anemll/models/qwen3-1.7b-ctx2048",
        help="Path to model"
    )
    parser.add_argument(
        "--turns",
        type=int,
        default=48,
        help="Number of turns in synthetic conversation (default: 48)"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=101,
        help="Random seed for synthetic generation (default: 101)"
    )
    parser.add_argument(
        "--chunk-sizes",
        type=str,
        default="1,2,4,8",
        help="Comma-separated chunk sizes to test (default: 1,2,4,8)"
    )

    args = parser.parse_args()
    chunk_sizes = [int(x) for x in args.chunk_sizes.split(',')]

    print("=" * 70)
    print("CHUNK-SIZE OPTIMIZATION TEST")
    print("=" * 70)
    print()
    print(f"Model: {args.model}")
    print(f"Synthetic turns: {args.turns}")
    print(f"Seed: {args.seed}")
    print(f"Chunk sizes: {chunk_sizes}")
    print()

    # Generate synthetic conversation
    print("Generating synthetic conversation...")
    turns, planted = generate_nanobot_conversation(args.turns, args.seed)
    print(f"Generated {len(turns)} turns with {len(planted)} planted facts")
    print()

    # Test each chunk size
    extractor = ChunkSizeExtractor(args.model)
    results = []

    for chunk_size in chunk_sizes:
        print(f"Testing chunk_size={chunk_size}...")

        if chunk_size == 1:
            extracted, metrics = extractor.extract_per_turn(turns)
        else:
            extracted, metrics = extractor.extract_chunked(turns, chunk_size)

        # Score recall
        recalled, missed = score_recall(extracted, planted)

        result = {
            'chunk_size': chunk_size,
            'metrics': metrics,
            'recall': len(recalled),
            'total_facts': len(planted),
            'recall_rate': len(recalled) / len(planted),
            'recalled': [f.text for f in recalled],
            'missed': [f.text for f in missed]
        }

        results.append(result)

        print(f"  Chunks: {metrics['num_chunks']}")
        print(f"  Total tokens: {metrics['total_tokens']}")
        print(f"  Recall: {len(recalled)}/{len(planted)} ({result['recall_rate']:.1%})")
        print()

    # Summary
    print("=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print()
    print(f"{'Chunk Size':<12} {'Chunks':<8} {'Tokens':<10} {'Recall':<10} {'Savings':<10}")
    print("-" * 70)

    baseline = results[0]
    for r in results:
        savings = 100 * (baseline['metrics']['total_tokens'] - r['metrics']['total_tokens']) / baseline['metrics']['total_tokens']
        print(f"{r['chunk_size']:<12} {r['metrics']['num_chunks']:<8} {r['metrics']['total_tokens']:<10} "
              f"{r['recall']}/{r['total_facts']:<8} {savings:>7.1f}%")

    print()
    print("=" * 70)
    print("ANALYSIS")
    print("=" * 70)
    print()

    # Find best chunk size (balance of savings and recall)
    best = None
    for r in results:
        if r['recall_rate'] >= 0.75:  # Acceptable recall threshold
            if best is None or r['metrics']['total_tokens'] < best['metrics']['total_tokens']:
                best = r

    if best:
        savings = 100 * (baseline['metrics']['total_tokens'] - best['metrics']['total_tokens']) / baseline['metrics']['total_tokens']
        print(f"✓ Best configuration: chunk_size={best['chunk_size']}")
        print(f"  Token savings: {savings:.1f}%")
        print(f"  Recall: {best['recall']}/{best['total_facts']} ({best['recall_rate']:.1%})")
        print(f"  Number of chunks: {best['metrics']['num_chunks']}")
    else:
        print("✗ No configuration met recall threshold (≥75%)")
    print()


if __name__ == "__main__":
    main()
```

---

## Testing Protocol

### Phase 1: Single-Seed Test (Quick Validation)

**Goal**: Confirm chunk-size effect exists on ANE

```bash
cd arms/arm_d
python3 test_chunk_size.py --turns 48 --seed 101 --chunk-sizes "1,2,4,8"
```

**Expected**:
- Chunk size 1 (baseline): highest tokens
- Chunk size 2-8: progressively fewer tokens
- Recall should stay ≥75%

**Success criteria**: Any chunk size >1 shows ≥20% token reduction with ≥75% recall

### Phase 2: Multi-Seed Confirmation (Rigor)

**Goal**: Confirm effect is reproducible, not seed-dependent

```bash
for seed in 101 202 303; do
    python3 test_chunk_size.py --turns 48 --seed $seed --chunk-sizes "1,2,4,8"
done
```

**Success criteria**:
- All 3 seeds show similar token reduction pattern
- Mean recall across seeds ≥75%
- No single seed fails completely

### Phase 3: Optimal Chunk Size

**Goal**: Find sweet spot for ANE (may differ from AMD's chunk32/48)

```bash
python3 test_chunk_size.py --turns 96 --seed 101 --chunk-sizes "1,2,4,6,8,12,16"
```

**Analysis**:
- Plot tokens vs chunk size
- Plot recall vs chunk size
- Find "knee" in curve (diminishing returns)

---

## Expected Outcomes

### Scenario A: Chunk-Size Works on ANE

**Result**: ≥30% token reduction with ≥75% recall at chunk_size≥4

**Action**:
1. Integrate into service.py
2. Stack with Budget 100 for combined savings
3. Document optimal chunk size for ANE

**Projected impact**:
- Budget 100 alone: 39% savings (251 → 153 tokens)
- Chunk-size alone: 30-50% savings (hypothetical)
- **Combined**: Potentially 60-70% total savings vs baseline

### Scenario B: Chunk-Size Doesn't Transfer

**Result**: Either recall collapses <75% or no token reduction

**Reasons** (possible):
- 1.7B model too small (AMD required 9B)
- ANE's overhead structure different
- Nanobot's turn content less redundant than AMD's fixtures

**Action**:
1. Document why it didn't work
2. Keep Budget 100 as primary optimization
3. Revisit if model upgraded to 8B

---

## Risk Mitigation

### Risk 1: Synthetic fixtures don't represent real conversations

**Mitigation**:
- Also test on real nanobot conversation samples
- Compare synthetic vs real results
- Adjust fixture generation if divergence found

### Risk 2: Recall scoring is too simplistic

**Mitigation**:
- Use substring matching (conservative)
- Manual review of first few results
- Compare against AMD's scoring approach

### Risk 3: Implementation too complex for production

**Mitigation**:
- Start with simple chunking (every N turns)
- Don't over-engineer
- Measure actual benefit before full integration

---

## Decision Gates

### Gate 1: After Phase 1 (Single-Seed)

**Go**: Token reduction ≥20% with recall ≥75%
→ Proceed to Phase 2

**No-Go**: Token reduction <20% OR recall <75%
→ Document and close, keep Budget 100

### Gate 2: After Phase 2 (Multi-Seed)

**Go**: Mean recall across 3 seeds ≥75%, token reduction ≥25%
→ Proceed to Phase 3

**No-Go**: Any seed fails dramatically OR mean recall <75%
→ Document as model-size dependent, revisit with 8B

### Gate 3: After Phase 3 (Optimal Size)

**Go**: Found optimal chunk size with good savings/recall balance
→ Integrate into service.py

**No-Go**: No clear optimal point OR integration too complex
→ Keep Budget 100, document findings

---

## Next Steps

**Immediate**:
1. Implement `synthetic_fixtures.py`
2. Implement `test_chunk_size.py`
3. Run Phase 1 test (single seed, quick)

**If Phase 1 passes**:
4. Run Phase 2 (multi-seed confirmation)
5. Run Phase 3 (find optimal)
6. Plan production integration

**Timeline**: 2-3 days for Phases 1-3
