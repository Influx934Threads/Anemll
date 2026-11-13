#!/usr/bin/env python3
"""
Test hybrid fallback for EntityDeduplicator

Tests the smart hybrid fallback that:
1. Uses string similarity for empty entities (pure prose)
2. Uses string similarity for sparse generic entities (words like "User")
3. Trusts Jaccard for sparse numeric entities (numbers like "30", "60")
"""
import sys
from pathlib import Path

# Add to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mrc_cpu_ops import EntityDeduplicator, MechanicalMerger


def test_empty_entities():
    """Test string fallback for pure prose (no entities)"""
    print("Test 1: Empty Entities (Pure Prose)")
    print("-" * 70)

    dedup = EntityDeduplicator(enable_fallback=True)

    facts = [
        {'type': 'preference', 'content': 'prefers concise responses'},
        {'type': 'preference', 'content': 'prefers concise responses'},  # Duplicate
        {'type': 'preference', 'content': 'likes detailed explanations'},  # Different
    ]

    result = dedup.deduplicate(facts)

    print(f"  Input: {len(facts)} facts")
    print(f"  Output: {len(result)} facts")
    print(f"  Expected: 2 (duplicate removed via string fallback)")

    assert len(result) == 2, f"Expected 2 facts, got {len(result)}"
    print("  ✅ PASS")
    print()

    return True


def test_sparse_generic_entities():
    """Test string fallback for sparse generic entities (words)"""
    print("Test 2: Sparse Generic Entities (Same Word, Different Content)")
    print("-" * 70)

    dedup = EntityDeduplicator(enable_fallback=True)

    facts = [
        {'type': 'context', 'content': 'User prefers concise responses'},
        {'type': 'context', 'content': 'User likes detailed explanations'},  # Different
        {'type': 'context', 'content': 'User prefers concise answers'},  # Similar to first
    ]

    result = dedup.deduplicate(facts)

    print(f"  Input: {len(facts)} facts")
    print(f"  Output: {len(result)} facts")
    print(f"  Expected: 2 (1st & 2nd different, 3rd merged with 1st via string)")

    assert len(result) == 2, f"Expected 2 facts, got {len(result)}"

    # Verify the right facts were kept
    contents = [f['content'] for f in result]
    assert 'User prefers concise responses' in contents
    assert 'User likes detailed explanations' in contents

    print("  ✅ PASS")
    print()

    return True


def test_sparse_numeric_entities():
    """Test Jaccard trust for sparse numeric entities (numbers)"""
    print("Test 3: Sparse Numeric Entities (Configuration Facts)")
    print("-" * 70)

    dedup = EntityDeduplicator(enable_fallback=True)

    facts = [
        {'type': 'config', 'content': 'timeout: 30s'},
        {'type': 'config', 'content': 'timeout set to 30s'},  # Same value, different wording
        {'type': 'config', 'content': 'timeout: 60s'},  # Different value
    ]

    # Show entity extraction
    for i, fact in enumerate(facts):
        entities = dedup._extract_entities(fact['content'])
        is_generic = dedup._has_only_generic_entities(entities)
        print(f"  Fact {i+1}: entities={entities}, generic={is_generic}")

    result = dedup.deduplicate(facts)

    print(f"\n  Input: {len(facts)} facts")
    print(f"  Output: {len(result)} facts")
    print(f"  Expected: 2 (30s variants merged via Jaccard, 60s preserved)")

    assert len(result) == 2, f"Expected 2 facts, got {len(result)}"

    # Verify correct facts kept
    contents = [f['content'] for f in result]
    assert any('30' in c for c in contents), "Should preserve one 30s fact"
    assert any('60' in c for c in contents), "Should preserve 60s fact"

    print(f"\n  Kept facts:")
    for i, fact in enumerate(result):
        print(f"    {i+1}. {fact['content']}")

    print("  ✅ PASS")
    print()

    return True


def test_complete_mechanical_merger():
    """Test complete MechanicalMerger with mixed fact types"""
    print("Test 4: Complete MechanicalMerger (Mixed Fact Types)")
    print("-" * 70)

    merger = MechanicalMerger(mode="entity")

    mixed_facts = [
        # Configuration facts with numbers (should merge 30s variants)
        {'type': 'config', 'content': 'timeout: 30s'},
        {'type': 'config', 'content': 'timeout set to 30s'},
        {'type': 'config', 'content': 'timeout: 60s'},
        # Prose facts with no entities (should merge duplicates)
        {'type': 'preference', 'content': 'prefers concise responses'},
        {'type': 'preference', 'content': 'prefers concise responses'},
        # Sparse generic entities (should keep different content)
        {'type': 'context', 'content': 'User prefers brevity'},
        {'type': 'context', 'content': 'User likes details'},
    ]

    result = merger.merge(mixed_facts)

    print(f"  Input: {len(mixed_facts)} facts")
    print(f"  Output: {result['num_unique_facts']} unique facts")
    print(f"  Duplicates removed: {result['duplicate_count']}")
    print(f"  Compression ratio: {result['compression_ratio']:.2f}x")
    print(f"  Expected: 5 unique facts (2 config, 1 preference, 2 context)")

    assert result['num_unique_facts'] == 5, f"Expected 5 unique facts, got {result['num_unique_facts']}"
    assert result['duplicate_count'] == 2, f"Expected 2 duplicates removed, got {result['duplicate_count']}"

    print("  ✅ PASS")
    print()

    return True


def test_fallback_disabled():
    """Test that fallback can be disabled"""
    print("Test 5: Fallback Disabled")
    print("-" * 70)

    dedup = EntityDeduplicator(enable_fallback=False)

    # Pure prose facts (no entities)
    facts = [
        {'type': 'preference', 'content': 'prefers concise responses'},
        {'type': 'preference', 'content': 'prefers concise responses'},  # Duplicate
    ]

    result = dedup.deduplicate(facts)

    print(f"  Input: {len(facts)} facts")
    print(f"  Output: {len(result)} facts")
    print(f"  Expected: 2 (fallback disabled, duplicates NOT detected)")

    # With fallback disabled, both should be kept (no string comparison)
    assert len(result) == 2, f"Expected 2 facts (no fallback), got {len(result)}"

    print("  ✅ PASS")
    print()

    return True


def main():
    """Run all tests"""
    print()
    print("=" * 70)
    print("EntityDeduplicator Hybrid Fallback Tests")
    print("=" * 70)
    print()

    tests = [
        test_empty_entities,
        test_sparse_generic_entities,
        test_sparse_numeric_entities,
        test_complete_mechanical_merger,
        test_fallback_disabled,
    ]

    results = []
    for test in tests:
        try:
            results.append(test())
        except AssertionError as e:
            print(f"  ❌ FAIL: {e}")
            print()
            results.append(False)
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            print()
            results.append(False)

    print("=" * 70)
    print("Test Summary")
    print("=" * 70)
    passed = sum(results)
    total = len(results)
    print(f"Tests Passed: {passed}/{total}")

    if all(results):
        print()
        print("✅ ALL TESTS PASSED")
        print()
        print("Hybrid Fallback Features:")
        print("  1. ✅ Empty entities → String similarity fallback")
        print("  2. ✅ Sparse generic entities (words) → String fallback")
        print("  3. ✅ Sparse numeric entities (numbers) → Trust Jaccard")
        print("  4. ✅ Complete MechanicalMerger integration")
        print("  5. ✅ Fallback can be disabled")
        print()
        return 0
    else:
        print()
        print(f"❌ {total - passed} TEST(S) FAILED")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
