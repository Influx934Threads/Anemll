#!/usr/bin/env python3
"""
EntityDeduplicator vs MechanicalMerger (string-based) comparison tests

Tests the hypothesis that entity-aware deduplication will:
1. Preserve facts with different numeric values (timeout 30s vs 60s)
2. Improve recall from 92.9% to ≥95%
3. Maintain acceptable compression (≥1.3x)
"""
import sys
from pathlib import Path
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from arms.arm_c.mechanical_merger import MechanicalMerger, EntityDeduplicator

# Test cases
TIMEOUT_CASE = [
    {"type": "configuration", "content": "timeout: 30s", "entities": []},
    {"type": "configuration", "content": "timeout: 60s", "entities": []},
]

API_RATE_CASE = [
    {"type": "configuration", "content": "API rate limit set to 100 requests per minute", "entities": ["API rate limit", "100 requests per minute"]},
    {"type": "configuration", "content": "API rate limit set to 100 requests per minute", "entities": ["API rate limit", "100"]},
    {"type": "configuration", "content": "API rate: 100 req/min", "entities": ["API", "100"]},
]

REPHRASE_CASE = [
    {"type": "result", "content": "The change has been applied and will take effect immediately", "entities": ["change"]},
    {"type": "result", "content": "Changes applied successfully", "entities": ["Changes"]},
    {"type": "result", "content": "The change has been applied and will take effect immediately", "entities": ["change", "API rate limit"]},
]

# Full ARM C dataset (14 facts)
ARM_C_FACTS = [
    {"type": "configuration", "content": "API rate limit set to 100 requests per minute", "entities": ["API rate limit", "100 requests per minute"]},
    {"type": "result", "content": "The change has been applied and will take effect immediately", "entities": ["change", "API rate limit"]},
    {"type": "configuration", "content": "timeout configuration set to 30 seconds", "entities": ["timeout", "30 seconds"]},
    {"type": "configuration", "content": "log level set to debug mode", "entities": ["log level", "debug mode"]},
    {"type": "configuration", "content": "database connection to PostgreSQL on port 5432", "entities": ["database", "PostgreSQL", "5432"]},
    {"type": "configuration", "content": "cache size set to 1024 MB", "entities": ["cache size", "1024 MB"]},
    {"type": "configuration", "content": "API rate limit set to 100 requests per minute", "entities": ["API rate limit", "100"]},
    {"type": "result", "content": "The change has been applied and will take effect immediately", "entities": ["change"]},
    {"type": "context", "content": "```json", "entities": []},
    {"type": "context", "content": "```", "entities": []},
    {"type": "configuration", "content": "timeout set to 30s", "entities": ["timeout", "30s"]},
    {"type": "configuration", "content": "timeout configured for 60 seconds", "entities": ["timeout", "60 seconds"]},
    {"type": "configuration", "content": "API rate: 100 req/min", "entities": ["API", "100"]},
    {"type": "result", "content": "Changes applied successfully", "entities": ["Changes"]},
]

def test_deduplicator(name: str, dedup_fn, facts: list) -> dict:
    """Test a deduplicator on given facts"""
    import time

    start = time.time()
    result = dedup_fn(facts)
    elapsed_ms = (time.time() - start) * 1000

    return {
        'name': name,
        'input_facts': len(facts),
        'output_facts': len(result),
        'duplicates_removed': len(facts) - len(result),
        'compression_ratio': len(facts) / len(result) if result else 0,
        'time_ms': elapsed_ms,
        'unique_facts': result
    }

def compare_approaches(test_name: str, facts: list):
    """Compare string-based vs entity-based on a test case"""
    print(f"\n{'='*80}")
    print(f"Test Case: {test_name}")
    print(f"{'='*80}\n")

    # String-based (current)
    merger = MechanicalMerger(similarity_threshold=0.85)
    string_result = test_deduplicator(
        "String-based (85%)",
        lambda f: merger._deduplicate_facts(f),
        facts
    )

    # Entity-based (new)
    entity_dedup = EntityDeduplicator()
    entity_result = test_deduplicator(
        "Entity-based (50% Jaccard)",
        entity_dedup.deduplicate,
        facts
    )

    # Show comparison
    print(f"{'Metric':<30} {'String-based':<20} {'Entity-based':<20} {'Winner':<15}")
    print("-" * 80)
    print(f"{'Input facts':<30} {string_result['input_facts']:<20} {entity_result['input_facts']:<20} {'-':<15}")
    print(f"{'Output facts':<30} {string_result['output_facts']:<20} {entity_result['output_facts']:<20} ", end="")

    if entity_result['output_facts'] > string_result['output_facts']:
        print("Entity (more preserved)")
    elif entity_result['output_facts'] < string_result['output_facts']:
        print("String (less preserved)")
    else:
        print("Tie")

    print(f"{'Duplicates removed':<30} {string_result['duplicates_removed']:<20} {entity_result['duplicates_removed']:<20} ", end="")

    if entity_result['duplicates_removed'] < string_result['duplicates_removed']:
        print("Entity (less aggressive)")
    elif entity_result['duplicates_removed'] > string_result['duplicates_removed']:
        print("String (less aggressive)")
    else:
        print("Tie")

    print(f"{'Compression ratio':<30} {string_result['compression_ratio']:<20.2f} {entity_result['compression_ratio']:<20.2f} ", end="")

    if entity_result['compression_ratio'] > string_result['compression_ratio']:
        print("Entity (higher)")
    elif entity_result['compression_ratio'] < string_result['compression_ratio']:
        print("String (higher)")
    else:
        print("Tie")

    print(f"{'Time (ms)':<30} {string_result['time_ms']:<20.2f} {entity_result['time_ms']:<20.2f} ", end="")

    if entity_result['time_ms'] < string_result['time_ms']:
        print("Entity (faster)")
    else:
        print("String (faster)")

    print()

    # Show detailed results
    print("String-based unique facts:")
    for i, fact in enumerate(string_result['unique_facts'], 1):
        print(f"  {i}. [{fact['type']}] {fact['content']}")

    print()
    print("Entity-based unique facts:")
    for i, fact in enumerate(entity_result['unique_facts'], 1):
        content = fact['content']
        # Show extracted entities
        entity_dedup = EntityDeduplicator()
        entities = entity_dedup._extract_entities(content)
        print(f"  {i}. [{fact['type']}] {content}")
        if entities:
            print(f"      Entities: {entities}")

    print()

    return string_result, entity_result

def test_timeout_preservation():
    """Critical test: Does entity-based preserve timeout 30s vs 60s?"""
    print(f"\n{'='*80}")
    print("CRITICAL TEST: Timeout 30s vs 60s Preservation")
    print(f"{'='*80}\n")

    print("Facts:")
    for fact in TIMEOUT_CASE:
        print(f"  - {fact['content']}")
    print()

    # String-based
    merger = MechanicalMerger(similarity_threshold=0.85)
    string_unique = merger._deduplicate_facts(TIMEOUT_CASE)

    # Entity-based
    entity_dedup = EntityDeduplicator()
    entity_unique = entity_dedup.deduplicate(TIMEOUT_CASE)

    print(f"String-based result: {len(string_unique)} unique facts")
    if len(string_unique) == 2:
        print("  ✓ CORRECT: Both timeouts preserved")
    else:
        print("  ✗ WRONG: Merged different values")

    print()
    print(f"Entity-based result: {len(entity_unique)} unique facts")
    if len(entity_unique) == 2:
        print("  ✓ CORRECT: Both timeouts preserved")
    else:
        print("  ✗ WRONG: Merged different values")

    print()

    # Show entity extraction
    entity_dedup = EntityDeduplicator()
    for fact in TIMEOUT_CASE:
        entities = entity_dedup._extract_entities(fact['content'])
        print(f"{fact['content']}")
        print(f"  → Entities: {entities}")

    print()

def main():
    """Run all tests"""
    print("="*80)
    print("EntityDeduplicator vs MechanicalMerger (String-based) Tests")
    print("="*80)

    # Phase 1: Critical timeout test
    test_timeout_preservation()

    # Phase 2: Test cases
    compare_approaches("API Rate Limit (should merge)", API_RATE_CASE)
    compare_approaches("Result Messages (should merge similar)", REPHRASE_CASE)

    # Phase 3: Full ARM C dataset
    string_result, entity_result = compare_approaches("Full ARM C Dataset (14 facts)", ARM_C_FACTS)

    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY: ARM C Dataset Comparison")
    print(f"{'='*80}\n")

    # Compare to baseline (from arm_c_merge_results.json)
    baseline_recall = 0.929  # 92.9%
    baseline_compression = 1.56

    # Calculate estimated recall (simple heuristic)
    # Assume 14 input facts, baseline keeps 9 with 92.9% recall (13 facts preserved)
    # So 1 fact was lost in the merge

    string_facts_kept = string_result['output_facts']
    entity_facts_kept = entity_result['output_facts']

    print(f"{'Metric':<30} {'Baseline':<15} {'String':<15} {'Entity':<15}")
    print("-" * 80)
    print(f"{'Compression ratio':<30} {baseline_compression:<15.2f} {string_result['compression_ratio']:<15.2f} {entity_result['compression_ratio']:<15.2f}")
    print(f"{'Output facts':<30} {'9':<15} {string_facts_kept:<15} {entity_facts_kept:<15}")
    print(f"{'Estimated recall':<30} {'92.9%':<15} {'~93%':<15} {'?':<15}")
    print()

    # Recommendation
    print(f"{'='*80}")
    print("RECOMMENDATION")
    print(f"{'='*80}\n")

    if entity_result['output_facts'] > string_result['output_facts']:
        improvement = entity_result['output_facts'] - string_result['output_facts']
        compression_loss = string_result['compression_ratio'] - entity_result['compression_ratio']

        print(f"✓ Entity-based preserves {improvement} more fact(s)")
        print(f"  Trade-off: {compression_loss:.2f}x less compression")
        print()

        if compression_loss < 0.2:
            print("→ RECOMMEND: Adopt EntityDeduplicator")
            print("  - Better recall with minimal compression loss")
            print("  - Correctly handles numeric value differences")
        else:
            print("→ RECOMMEND: Make it configurable")
            print("  - High precision mode: entity-based")
            print("  - High compression mode: string-based")
    else:
        print("✗ Entity-based does not improve fact preservation")
        print("→ RECOMMEND: Keep string-based MechanicalMerger")
        print("  - No measurable benefit from entity-based approach")

    print()

if __name__ == "__main__":
    main()
