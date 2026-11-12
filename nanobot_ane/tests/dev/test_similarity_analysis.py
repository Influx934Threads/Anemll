#!/usr/bin/env python3
"""
Analyze actual similarity scores between timeout facts
to understand where the 85% vs 86% threshold matters
"""
import sys
from pathlib import Path
from difflib import SequenceMatcher

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Timeout facts that might be close
timeout_facts = [
    "timeout configuration set to 30 seconds",
    "timeout set to 30s",
    "timeout configured for 60 seconds",
    "timeout set to 60 seconds",
    "timeout: 30s",
    "timeout: 60s",
]

def similarity(text1: str, text2: str) -> float:
    """Compute similarity (same as MechanicalMerger)"""
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()

def analyze_similarities():
    """Show all pairwise similarities"""
    print("=" * 80)
    print("Pairwise Similarity Analysis - Timeout Facts")
    print("=" * 80)
    print()

    # Create similarity matrix
    print(f"{'Fact 1':<45} {'Fact 2':<45} {'Similarity':>10}")
    print("-" * 80)

    critical_pairs = []

    for i, fact1 in enumerate(timeout_facts):
        for j, fact2 in enumerate(timeout_facts):
            if i < j:  # Only upper triangle
                sim = similarity(fact1, fact2)
                marker = ""

                # Highlight critical ranges
                if 0.85 <= sim < 0.86:
                    marker = " ← BETWEEN 85-86%!"
                    critical_pairs.append((fact1, fact2, sim))
                elif 0.84 <= sim < 0.85:
                    marker = " ← Just below 85%"
                elif sim >= 0.86:
                    marker = " ← Above 86%"

                print(f"{fact1:<45} {fact2:<45} {sim:>9.2%}{marker}")

    print()

    if critical_pairs:
        print("=" * 80)
        print(f"CRITICAL: Found {len(critical_pairs)} pair(s) in 85%-86% range")
        print("=" * 80)
        print()
        for fact1, fact2, sim in critical_pairs:
            print(f"Similarity: {sim:.4f} ({sim:.2%})")
            print(f"  Fact 1: {fact1}")
            print(f"  Fact 2: {fact2}")
            print()
            print(f"  At 85% threshold: Would merge (lose one)")
            print(f"  At 86% threshold: Would keep separate (preserve both)")
            print()
    else:
        print("=" * 80)
        print("No pairs found in 85%-86% range")
        print("=" * 80)
        print()
        print("This means:")
        print("  - Either facts are <85% similar (kept separate at both thresholds)")
        print("  - Or facts are >86% similar (merged at both thresholds)")
        print()

    # Show examples of different vs same value timeouts
    print("=" * 80)
    print("Key Examples: Same value vs Different value")
    print("=" * 80)
    print()

    # Same value (30s)
    same_value_pairs = [
        ("timeout configuration set to 30 seconds", "timeout set to 30s"),
        ("timeout configuration set to 30 seconds", "timeout: 30s"),
    ]

    # Different values (30s vs 60s)
    diff_value_pairs = [
        ("timeout configuration set to 30 seconds", "timeout configured for 60 seconds"),
        ("timeout set to 30s", "timeout set to 60 seconds"),
        ("timeout: 30s", "timeout: 60s"),
    ]

    print("Same value (should merge):")
    for fact1, fact2 in same_value_pairs:
        sim = similarity(fact1, fact2)
        should_merge_85 = sim >= 0.85
        should_merge_86 = sim >= 0.86
        print(f"  {sim:.2%}: {fact1} ≈ {fact2}")
        print(f"    85%: {'MERGE' if should_merge_85 else 'KEEP'}")
        print(f"    86%: {'MERGE' if should_merge_86 else 'KEEP'}")
        print()

    print("Different values (should NOT merge):")
    for fact1, fact2 in diff_value_pairs:
        sim = similarity(fact1, fact2)
        should_merge_85 = sim >= 0.85
        should_merge_86 = sim >= 0.86
        print(f"  {sim:.2%}: {fact1} ≠ {fact2}")
        print(f"    85%: {'MERGE ✗ WRONG!' if should_merge_85 else 'KEEP ✓'}")
        print(f"    86%: {'MERGE ✗ WRONG!' if should_merge_86 else 'KEEP ✓'}")
        print()

if __name__ == "__main__":
    analyze_similarities()
