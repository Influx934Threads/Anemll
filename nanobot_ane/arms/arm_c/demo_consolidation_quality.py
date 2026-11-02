#!/usr/bin/env python3
"""
Demo: Quality-check mechanical merge consolidation with pre-extracted facts.

Demonstrates the quality checking process without requiring model inference.
"""
import sys
from pathlib import Path
from typing import List, Dict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mechanical_merger import MechanicalMerger


def check_fact_retention(original_facts: List[Dict], consolidated_text: str) -> Dict:
    """
    Check which facts are retained in consolidated text.

    Uses keyword matching to determine if fact content appears in summary.
    """
    consolidated_lower = consolidated_text.lower()

    preserved = []
    lost = []

    for fact in original_facts:
        content = fact.get('content', '').lower()
        fact_type = fact.get('type', 'unknown')

        # Extract key words (longer than 4 chars, excluding common words)
        common_words = {'this', 'that', 'with', 'from', 'have', 'been', 'will', 'would', 'should'}
        key_words = [
            w for w in content.split()
            if len(w) > 4 and w not in common_words
        ]

        # Check if at least 2 key words appear in consolidated text
        matches = sum(1 for word in key_words[:5] if word in consolidated_lower)

        if matches >= min(2, len(key_words)):
            preserved.append({
                'type': fact_type,
                'content': fact.get('content', ''),
                'matches': matches,
                'key_words': key_words[:5]
            })
        else:
            lost.append({
                'type': fact_type,
                'content': fact.get('content', ''),
                'matches': matches,
                'key_words': key_words[:5]
            })

    total = len(original_facts)
    recall = len(preserved) / total if total > 0 else 0

    return {
        'preserved': preserved,
        'lost': lost,
        'total_facts': total,
        'preserved_count': len(preserved),
        'lost_count': len(lost),
        'recall': recall
    }


def analyze_by_type(original_facts: List[Dict], quality_results: Dict) -> Dict:
    """Analyze retention by fact type"""
    by_type = {}

    # Count original facts by type
    for fact in original_facts:
        fact_type = fact.get('type', 'unknown')
        if fact_type not in by_type:
            by_type[fact_type] = {'total': 0, 'preserved': 0, 'lost': 0}
        by_type[fact_type]['total'] += 1

    # Count preserved by type
    for fact in quality_results['preserved']:
        fact_type = fact['type']
        by_type[fact_type]['preserved'] += 1

    # Count lost by type
    for fact in quality_results['lost']:
        fact_type = fact['type']
        by_type[fact_type]['lost'] += 1

    # Calculate recall per type
    for fact_type in by_type:
        total = by_type[fact_type]['total']
        preserved = by_type[fact_type]['preserved']
        by_type[fact_type]['recall'] = preserved / total if total > 0 else 0

    return by_type


def print_report(
    original_facts: List[Dict],
    merge_result: Dict,
    quality_results: Dict,
    by_type_results: Dict
):
    """Print detailed quality report"""
    print("\n" + "=" * 70)
    print("CONSOLIDATION QUALITY REPORT")
    print("=" * 70)
    print()

    # Input stats
    print("INPUT:")
    print(f"  Original facts: {len(original_facts)}")
    print(f"  Fact types: {len(set(f.get('type', 'unknown') for f in original_facts))}")
    print()

    # Consolidation stats
    print("CONSOLIDATION:")
    print(f"  Output facts: {merge_result['num_unique_facts']}")
    print(f"  Duplicates removed: {merge_result['duplicate_count']}")
    print(f"  Compression ratio: {merge_result['compression_ratio']:.2f}x")
    print(f"  Output length: {len(merge_result['text'])} chars")
    print()

    # Quality metrics
    print("QUALITY METRICS:")
    print(f"  Facts preserved: {quality_results['preserved_count']}/{quality_results['total_facts']}")
    print(f"  Facts lost: {quality_results['lost_count']}/{quality_results['total_facts']}")
    print(f"  Recall: {quality_results['recall']:.1%}")
    print()

    # By-type analysis
    print("RETENTION BY FACT TYPE:")
    print(f"  {'Type':<15} {'Total':>7} {'Preserved':>10} {'Lost':>7} {'Recall':>8}")
    print("  " + "-" * 60)
    for fact_type in sorted(by_type_results.keys()):
        stats = by_type_results[fact_type]
        print(f"  {fact_type:<15} {stats['total']:>7} {stats['preserved']:>10} "
              f"{stats['lost']:>7} {stats['recall']:>7.1%}")
    print()

    # Consolidated output
    print("CONSOLIDATED OUTPUT:")
    print("-" * 70)
    print(merge_result['text'])
    print("-" * 70)
    print()

    # Show lost facts if any
    if quality_results['lost']:
        print("⚠️  LOST FACTS (not found in consolidated output):")
        print("-" * 70)
        for i, fact in enumerate(quality_results['lost'][:10], 1):
            print(f"{i}. [{fact['type']}] {fact['content']}")
            print(f"   Key words checked: {', '.join(fact['key_words'])}")
            print()
        if len(quality_results['lost']) > 10:
            print(f"... and {len(quality_results['lost']) - 10} more")
        print()

    # Show some preserved facts
    if quality_results['preserved']:
        print("✓ PRESERVED FACTS (sample - found in consolidated output):")
        print("-" * 70)
        for i, fact in enumerate(quality_results['preserved'][:5], 1):
            print(f"{i}. [{fact['type']}] {fact['content']}")
            print(f"   Matched {fact['matches']} key words: {', '.join(fact['key_words'])}")
            print()
        if len(quality_results['preserved']) > 5:
            print(f"... and {len(quality_results['preserved']) - 5} more")
        print()

    # Overall assessment
    print("=" * 70)
    print("ASSESSMENT:")
    print("=" * 70)
    if quality_results['recall'] >= 0.90:
        print("✓ EXCELLENT - >90% fact retention")
    elif quality_results['recall'] >= 0.75:
        print("✓ GOOD - >75% fact retention")
    elif quality_results['recall'] >= 0.60:
        print("~ ACCEPTABLE - >60% fact retention")
    else:
        print("✗ POOR - <60% fact retention")
    print()


def demo_with_sample_facts():
    """Demo with pre-extracted sample facts from ARM C test"""

    # These are the actual facts from the ARM C test
    sample_facts = [
        {"type": "configuration", "content": "API rate limit set to 100 requests per minute", "entities": ["API rate limit", "100 requests per minute"]},
        {"type": "result", "content": "The change has been applied and will take effect immediately", "entities": ["change", "API rate limit", "100 requests per minute"]},
        {"type": "configuration", "content": "timeout configuration set to 30 seconds", "entities": ["timeout", "30 seconds"]},
        {"type": "result", "content": "timeout has been configured", "entities": ["timeout", "30 seconds"]},
        {"type": "configuration", "content": "log level set to debug mode", "entities": ["log level", "debug"]},
        {"type": "result", "content": "debug information will now be visible in logs", "entities": ["debug", "logs"]},
        {"type": "configuration", "content": "database connection to PostgreSQL on port 5432", "entities": ["database", "PostgreSQL", "port 5432"]},
        {"type": "result", "content": "connected to PostgreSQL database", "entities": ["PostgreSQL", "database"]},
        {"type": "configuration", "content": "cache size set to 1024 MB", "entities": ["cache size", "1024 MB"]},
        {"type": "result", "content": "cache size has been configured", "entities": ["cache size", "1024 MB"]},
        # Add some duplicates to show deduplication
        {"type": "configuration", "content": "API rate limit configured to 100 requests per minute", "entities": ["API rate limit", "100"]},
        {"type": "configuration", "content": "timeout is 30 seconds", "entities": ["timeout", "30 seconds"]},
        {"type": "configuration", "content": "PostgreSQL connection on port 5432", "entities": ["PostgreSQL", "5432"]},
        {"type": "result", "content": "changes applied immediately", "entities": ["changes"]},
    ]

    print("=" * 70)
    print("MECHANICAL MERGE CONSOLIDATION QUALITY CHECK - DEMO")
    print("=" * 70)
    print()
    print(f"Sample facts: {len(sample_facts)}")
    print()

    # Step 1: Show input facts
    print("INPUT FACTS:")
    print("-" * 70)
    for i, fact in enumerate(sample_facts, 1):
        print(f"{i}. [{fact['type']}] {fact['content']}")
    print()

    # Step 2: Run mechanical merge
    print("Step 1: Running mechanical merge...")
    print("-" * 70)
    merger = MechanicalMerger(similarity_threshold=0.85)
    merge_result = merger.merge(sample_facts)
    print(f"✓ Consolidation complete")
    print(f"  Input: {len(sample_facts)} facts")
    print(f"  Output: {merge_result['num_unique_facts']} unique facts")
    print(f"  Duplicates removed: {merge_result['duplicate_count']}")
    print(f"  Compression: {merge_result['compression_ratio']:.2f}x")
    print()

    # Step 3: Check quality
    print("Step 2: Checking fact retention...")
    print("-" * 70)
    quality_results = check_fact_retention(sample_facts, merge_result['text'])
    by_type_results = analyze_by_type(sample_facts, quality_results)
    print(f"✓ Quality check complete")
    print()

    # Print detailed report
    print_report(sample_facts, merge_result, quality_results, by_type_results)


if __name__ == "__main__":
    demo_with_sample_facts()
