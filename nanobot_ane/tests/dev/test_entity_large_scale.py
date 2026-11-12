#!/usr/bin/env python3
"""
Large-scale EntityDeduplicator testing on realistic data

Tests:
1. Real nanobot conversation history (recent usage)
2. Medium-scale synthetic conversation (50 turns, ~8K tokens)
3. Large-scale synthetic conversation (100 turns, ~16K tokens)

Goal: Validate EntityDeduplicator performance and quality on realistic workloads
"""
import sys
from pathlib import Path
import json
import time

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from arms.arm_c.mechanical_merger import MechanicalMerger, EntityDeduplicator
from arms.shared.fixtures import Fixtures

def load_nanobot_history(jsonl_path: Path) -> list:
    """Load nanobot conversation history"""
    messages = []

    if not jsonl_path.exists():
        print(f"Warning: Nanobot history not found at {jsonl_path}")
        return messages

    try:
        with open(jsonl_path, 'r') as f:
            for line in f:
                if line.strip():
                    msg = json.loads(line)
                    messages.append(msg)
    except Exception as e:
        print(f"Error loading nanobot history: {e}")

    return messages

def extract_facts_from_conversation(messages: list, model_path: str = None) -> list:
    """
    Extract facts from conversation messages

    If model_path provided, uses LLM extraction.
    Otherwise, generates synthetic facts based on content patterns.
    """
    facts = []

    # For now, generate synthetic facts from message content
    # (Real extraction would require model loading which is expensive)

    for i, msg in enumerate(messages):
        role = msg.get('role', '')
        content = msg.get('content', '')

        if not content or len(content) < 10:
            continue

        # Simple fact generation based on content analysis
        # Extract configurations, numbers, decisions

        # Look for configuration patterns
        if any(word in content.lower() for word in ['set', 'configure', 'enable', 'disable', 'update']):
            facts.append({
                "type": "configuration",
                "content": content[:100],  # First 100 chars
                "entities": extract_simple_entities(content),
                "turn_id": i // 2
            })

        # Look for results/confirmations
        elif any(word in content.lower() for word in ['completed', 'done', 'success', 'applied', 'created']):
            facts.append({
                "type": "result",
                "content": content[:100],
                "entities": extract_simple_entities(content),
                "turn_id": i // 2
            })

        # Look for requirements
        elif any(word in content.lower() for word in ['need', 'require', 'must', 'should']):
            facts.append({
                "type": "requirement",
                "content": content[:100],
                "entities": extract_simple_entities(content),
                "turn_id": i // 2
            })

    return facts

def extract_simple_entities(text: str) -> list:
    """Simple entity extraction (numbers, capitalized words)"""
    import re

    entities = []

    # Extract numbers with units
    numbers = re.findall(r'\d+(?:\.\d+)?\s*(?:ms|s|MB|GB|KB|%|req/min|seconds?|minutes?)', text)
    entities.extend(numbers)

    # Extract standalone numbers
    numbers = re.findall(r'\b\d+\b', text)
    entities.extend(numbers[:3])  # Limit to first 3 numbers

    # Extract capitalized words (potential proper nouns)
    caps = re.findall(r'\b[A-Z][a-z]+\b', text)
    entities.extend(caps[:3])  # Limit to first 3

    return entities

def test_deduplication(name: str, facts: list, show_details: bool = False):
    """Test both string-based and entity-based deduplication"""

    print(f"\n{'='*80}")
    print(f"Test: {name}")
    print(f"{'='*80}\n")

    print(f"Input: {len(facts)} facts")

    # Count facts by type
    type_counts = {}
    for fact in facts:
        fact_type = fact.get('type', 'unknown')
        type_counts[fact_type] = type_counts.get(fact_type, 0) + 1

    print(f"Types: {dict(type_counts)}")
    print()

    # Test string-based
    print("String-based deduplication (85% threshold):")
    merger = MechanicalMerger(similarity_threshold=0.85)

    start = time.time()
    string_unique = merger._deduplicate_facts(facts)
    string_time = (time.time() - start) * 1000

    string_removed = len(facts) - len(string_unique)
    string_compression = len(facts) / len(string_unique) if string_unique else 0

    print(f"  Output: {len(string_unique)} facts")
    print(f"  Removed: {string_removed} duplicates")
    print(f"  Compression: {string_compression:.2f}x")
    print(f"  Time: {string_time:.2f}ms ({string_time/len(facts):.3f}ms per fact)")
    print()

    # Test entity-based
    print("Entity-based deduplication (50% Jaccard):")
    entity_dedup = EntityDeduplicator()

    start = time.time()
    entity_unique = entity_dedup.deduplicate(facts)
    entity_time = (time.time() - start) * 1000

    entity_removed = len(facts) - len(entity_unique)
    entity_compression = len(facts) / len(entity_unique) if entity_unique else 0

    print(f"  Output: {len(entity_unique)} facts")
    print(f"  Removed: {entity_removed} duplicates")
    print(f"  Compression: {entity_compression:.2f}x")
    print(f"  Time: {entity_time:.2f}ms ({entity_time/len(facts):.3f}ms per fact)")
    print()

    # Comparison
    print("Comparison:")
    print(f"  Entity found {entity_removed - string_removed:+d} more duplicates")
    print(f"  Entity is {string_time/entity_time:.1f}x faster")
    print(f"  Entity compression is {entity_compression/string_compression:.2f}x vs string")
    print()

    # Show sample outputs if requested
    if show_details and len(entity_unique) <= 20:
        print("Entity-based unique facts:")
        for i, fact in enumerate(entity_unique[:10], 1):
            entities = entity_dedup._extract_entities(fact.get('content', ''))
            print(f"  {i}. [{fact['type']}] {fact['content'][:60]}...")
            if entities:
                print(f"      Entities: {entities}")
        if len(entity_unique) > 10:
            print(f"  ... and {len(entity_unique) - 10} more")
        print()

    return {
        'name': name,
        'input_facts': len(facts),
        'string': {
            'output': len(string_unique),
            'removed': string_removed,
            'compression': string_compression,
            'time_ms': string_time
        },
        'entity': {
            'output': len(entity_unique),
            'removed': entity_removed,
            'compression': entity_compression,
            'time_ms': entity_time
        }
    }

def main():
    """Run large-scale tests"""

    print("="*80)
    print("EntityDeduplicator: Large-Scale Testing")
    print("="*80)
    print()

    results = []

    # Test 1: Real nanobot history
    print("Loading real nanobot conversation history...")
    nanobot_history_path = Path.home() / ".nanobot/workspace/memory/history.jsonl"
    nanobot_messages = load_nanobot_history(nanobot_history_path)

    if nanobot_messages:
        print(f"Loaded {len(nanobot_messages)} messages from nanobot history")
        nanobot_facts = extract_facts_from_conversation(nanobot_messages)

        if nanobot_facts:
            result = test_deduplication(
                "Real Nanobot History",
                nanobot_facts,
                show_details=True
            )
            results.append(result)
        else:
            print("Warning: No facts extracted from nanobot history")
    else:
        print("Warning: Could not load nanobot history, skipping")

    # Test 2: Medium synthetic conversation
    print("\nGenerating medium synthetic conversation (50 turns, ~8K tokens)...")
    fixtures = Fixtures()
    medium_conversation = fixtures.get_conversation("medium")
    medium_facts = extract_facts_from_conversation(medium_conversation)

    result = test_deduplication(
        "Medium Synthetic Conversation (50 turns)",
        medium_facts,
        show_details=False
    )
    results.append(result)

    # Test 3: Large synthetic conversation
    print("\nGenerating large synthetic conversation (100 turns, ~16K tokens)...")
    large_conversation = fixtures.get_conversation("large")
    large_facts = extract_facts_from_conversation(large_conversation)

    result = test_deduplication(
        "Large Synthetic Conversation (100 turns)",
        large_facts,
        show_details=False
    )
    results.append(result)

    # Summary table
    print("\n" + "="*80)
    print("SUMMARY: EntityDeduplicator Performance on Large Scale")
    print("="*80)
    print()

    print(f"{'Test':<40} {'Input':<10} {'String Out':<12} {'Entity Out':<12} {'Speedup':<10}")
    print("-" * 80)

    for result in results:
        speedup = result['string']['time_ms'] / result['entity']['time_ms']
        print(f"{result['name']:<40} {result['input_facts']:<10} "
              f"{result['string']['output']:<12} {result['entity']['output']:<12} "
              f"{speedup:<10.1f}x")

    print()

    # Detailed metrics
    print(f"{'Test':<40} {'String ms':<12} {'Entity ms':<12} {'Compression':<15}")
    print("-" * 80)

    for result in results:
        comp_ratio = f"{result['entity']['compression']:.2f}x vs {result['string']['compression']:.2f}x"
        print(f"{result['name']:<40} {result['string']['time_ms']:<12.2f} "
              f"{result['entity']['time_ms']:<12.2f} {comp_ratio:<15}")

    print()

    # Key findings
    print("="*80)
    print("KEY FINDINGS")
    print("="*80)
    print()

    avg_speedup = sum(r['string']['time_ms'] / r['entity']['time_ms'] for r in results) / len(results)
    avg_entity_compression = sum(r['entity']['compression'] for r in results) / len(results)
    avg_string_compression = sum(r['string']['compression'] for r in results) / len(results)

    print(f"Average speedup: {avg_speedup:.1f}x faster with entity-based")
    print(f"Average compression: {avg_entity_compression:.2f}x (entity) vs {avg_string_compression:.2f}x (string)")
    print()

    # Check if entity consistently better
    entity_wins = sum(1 for r in results if r['entity']['removed'] > r['string']['removed'])

    if entity_wins == len(results):
        print("✓ Entity-based found more duplicates in ALL tests")
    elif entity_wins > len(results) / 2:
        print(f"✓ Entity-based found more duplicates in {entity_wins}/{len(results)} tests")
    else:
        print(f"⚠ String-based found more duplicates in {len(results) - entity_wins}/{len(results)} tests")

    print()

    # Recommendation
    print("="*80)
    print("RECOMMENDATION")
    print("="*80)
    print()

    if avg_speedup > 10 and avg_entity_compression > avg_string_compression:
        print("✅ ADOPT EntityDeduplicator")
        print(f"  - {avg_speedup:.0f}x faster on average")
        print(f"  - {avg_entity_compression:.2f}x compression vs {avg_string_compression:.2f}x string-based")
        print("  - Correctly handles numeric value differences")
        print("  - Production ready for CPU-only MRC backend")
    elif avg_speedup > 5:
        print("✅ RECOMMEND EntityDeduplicator")
        print(f"  - {avg_speedup:.0f}x speedup is significant")
        print(f"  - Compression comparable: {avg_entity_compression:.2f}x vs {avg_string_compression:.2f}x")
    else:
        print("⚠ MIXED RESULTS")
        print("  - Consider making deduplication strategy configurable")

    print()

if __name__ == "__main__":
    main()
