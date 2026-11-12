#!/usr/bin/env python3
"""
Quick test comparing 85% vs 86% similarity thresholds
for mechanical merge deduplication
"""
import sys
from pathlib import Path
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from arms.arm_c.mechanical_merger import MechanicalMerger

# Sample facts from ARM C test (14 facts)
test_facts = [
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

def test_threshold(threshold: float, facts: list) -> dict:
    """Test mechanical merge with given threshold"""
    merger = MechanicalMerger(similarity_threshold=threshold)
    result = merger.merge(facts)

    return {
        'threshold': threshold,
        'input_facts': len(facts),
        'output_facts': result['num_unique_facts'],
        'duplicates_removed': result['duplicate_count'],
        'compression_ratio': result['compression_ratio'],
        'unique_facts': result['facts']
    }

def show_comparison():
    """Compare 85% vs 86% thresholds"""
    print("=" * 70)
    print("Mechanical Merge: Threshold Comparison")
    print("=" * 70)
    print()

    # Test both thresholds
    result_85 = test_threshold(0.85, test_facts)
    result_86 = test_threshold(0.86, test_facts)

    print(f"{'Metric':<25} {'85% (current)':<20} {'86% (test)':<20}")
    print("-" * 70)
    print(f"{'Input facts':<25} {result_85['input_facts']:<20} {result_86['input_facts']:<20}")
    print(f"{'Output facts':<25} {result_85['output_facts']:<20} {result_86['output_facts']:<20}")
    print(f"{'Duplicates removed':<25} {result_85['duplicates_removed']:<20} {result_86['duplicates_removed']:<20}")
    print(f"{'Compression ratio':<25} {result_85['compression_ratio']:<20.2f} {result_86['compression_ratio']:<20.2f}")
    print()

    # Show what changed
    print("=" * 70)
    print("What changed at 86%?")
    print("=" * 70)
    print()

    # Compare unique fact counts by type
    def count_by_type(facts):
        counts = {}
        for fact in facts:
            fact_type = fact.get('type', 'unknown')
            counts[fact_type] = counts.get(fact_type, 0) + 1
        return counts

    counts_85 = count_by_type(result_85['unique_facts'])
    counts_86 = count_by_type(result_86['unique_facts'])

    print(f"{'Fact Type':<20} {'85% count':<15} {'86% count':<15} {'Change':<10}")
    print("-" * 70)

    all_types = set(counts_85.keys()) | set(counts_86.keys())
    for fact_type in sorted(all_types):
        count_85 = counts_85.get(fact_type, 0)
        count_86 = counts_86.get(fact_type, 0)
        change = count_86 - count_85
        change_str = f"{change:+d}" if change != 0 else "="
        print(f"{fact_type:<20} {count_85:<15} {count_86:<15} {change_str:<10}")

    print()

    # Look for the timeout example specifically
    print("=" * 70)
    print("Timeout facts analysis:")
    print("=" * 70)
    print()

    for threshold_name, result in [("85%", result_85), ("86%", result_86)]:
        print(f"{threshold_name} threshold timeout facts:")
        timeout_facts = [f for f in result['unique_facts'] if 'timeout' in f.get('content', '').lower()]
        for i, fact in enumerate(timeout_facts, 1):
            print(f"  {i}. {fact.get('content', '')}")
        print()

    # Check if we caught the 30s vs 60s difference
    timeout_30s_variants = [
        "timeout configuration set to 30 seconds",
        "timeout set to 30s"
    ]
    timeout_60s = "timeout configured for 60 seconds"

    print("Key question: Did we preserve both 30s and 60s timeouts?")
    print()

    for threshold_name, result in [("85%", result_85), ("86%", result_86)]:
        contents = [f.get('content', '') for f in result['unique_facts']]
        has_30s = any(variant in contents for variant in timeout_30s_variants)
        has_60s = timeout_60s in contents
        print(f"{threshold_name}: 30s={has_30s}, 60s={has_60s}, Both preserved={has_30s and has_60s}")

    print()

    # Recommendation
    print("=" * 70)
    print("Recommendation:")
    print("=" * 70)
    print()

    diff_facts = result_86['output_facts'] - result_85['output_facts']
    diff_compression = result_85['compression_ratio'] - result_86['compression_ratio']

    if diff_facts > 0:
        print(f"✓ 86% threshold preserves {diff_facts} more fact(s)")
        print(f"  Trade-off: {diff_compression:.2f}x less compression")
        print()
        if diff_compression < 0.1:
            print("  → RECOMMEND 86%: Better recall, minimal compression loss")
        else:
            print("  → EVALUATE: Check if the preserved facts are meaningful")
    else:
        print(f"✗ No difference: Both thresholds produce same output")
        print(f"  → KEEP 85%: No benefit from tighter threshold")

    print()

if __name__ == "__main__":
    show_comparison()
