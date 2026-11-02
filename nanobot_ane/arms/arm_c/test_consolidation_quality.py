#!/usr/bin/env python3
"""
Quality-check script for mechanical merge consolidation.

Validates that key facts are preserved during consolidation by:
1. Extracting facts from a conversation
2. Running mechanical merge
3. Checking fact retention in the output
4. Reporting quality metrics
"""
import sys
from pathlib import Path
from typing import List, Dict, Tuple
import json

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mechanical_merger import MechanicalMerger
from structured_extractor import StructuredFactExtractor


class ConsolidationQualityChecker:
    """Check quality of mechanical merge consolidation"""

    def __init__(self, model_path: str):
        self.extractor = StructuredFactExtractor(model_path)
        self.merger = MechanicalMerger(similarity_threshold=0.85)

    def extract_facts_from_conversation(self, messages: List[Dict]) -> Tuple[List[Dict], List[str]]:
        """
        Extract facts from conversation messages.

        Returns:
            (all_facts, turn_texts): List of facts and original turn texts
        """
        all_facts = []
        turn_texts = []

        # Process message pairs as turns
        for i in range(0, len(messages) - 1, 2):
            if messages[i]['role'] == 'user' and messages[i+1]['role'] == 'assistant':
                turn_text = f"User: {messages[i]['content']}\nAssistant: {messages[i+1]['content']}"
                turn_texts.append(turn_text)

                # Extract facts from this turn
                facts, _ = self.extractor.extract_facts(turn_text)
                all_facts.extend(facts)

                print(f"Turn {len(turn_texts)}: Extracted {len(facts)} facts")

        return all_facts, turn_texts

    def consolidate(self, facts: List[Dict]) -> Dict:
        """Run mechanical merge consolidation"""
        return self.merger.merge(facts)

    def check_fact_retention(self, original_facts: List[Dict], consolidated_text: str) -> Dict:
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

    def analyze_by_type(self, original_facts: List[Dict], quality_results: Dict) -> Dict:
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
        self,
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


def test_with_sample_conversation():
    """Test with a sample conversation"""

    sample_messages = [
        {
            "role": "user",
            "content": "Set the API rate limit to 100 requests per minute"
        },
        {
            "role": "assistant",
            "content": "I've set the API rate limit to 100 requests per minute. The change has been applied and will take effect immediately."
        },
        {
            "role": "user",
            "content": "Also set the timeout to 30 seconds"
        },
        {
            "role": "assistant",
            "content": "Done. I've configured the timeout to 30 seconds."
        },
        {
            "role": "user",
            "content": "Set log level to debug"
        },
        {
            "role": "assistant",
            "content": "Log level has been set to debug mode. You'll now see detailed debug information in the logs."
        },
        {
            "role": "user",
            "content": "Connect to PostgreSQL on port 5432"
        },
        {
            "role": "assistant",
            "content": "Connected to PostgreSQL database on port 5432."
        },
        {
            "role": "user",
            "content": "Set cache size to 1024 MB"
        },
        {
            "role": "assistant",
            "content": "Cache size has been set to 1024 MB."
        }
    ]

    return sample_messages


def main():
    """Run consolidation quality check"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Quality-check mechanical merge consolidation"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="/Users/agundez/Build/Anemll/models/qwen3-1.7b-ctx2048",
        help="Path to model for fact extraction"
    )
    parser.add_argument(
        "--conversation",
        type=str,
        help="Path to JSON file with conversation messages"
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Use built-in sample conversation"
    )

    args = parser.parse_args()

    print("=" * 70)
    print("MECHANICAL MERGE CONSOLIDATION QUALITY CHECK")
    print("=" * 70)
    print()

    # Initialize checker
    print(f"Loading model: {args.model}")
    checker = ConsolidationQualityChecker(args.model)
    print()

    # Load conversation
    if args.sample or not args.conversation:
        print("Using sample conversation (5 turns)")
        messages = test_with_sample_conversation()
    else:
        print(f"Loading conversation from: {args.conversation}")
        with open(args.conversation, 'r') as f:
            data = json.load(f)
            messages = data if isinstance(data, list) else data.get('messages', [])

    print(f"Conversation: {len(messages)} messages")
    print()

    # Step 1: Extract facts
    print("Step 1: Extracting facts from conversation...")
    print("-" * 70)
    original_facts, turn_texts = checker.extract_facts_from_conversation(messages)
    print()
    print(f"✓ Extracted {len(original_facts)} facts from {len(turn_texts)} turns")
    print()

    # Step 2: Consolidate
    print("Step 2: Running mechanical merge...")
    print("-" * 70)
    merge_result = checker.consolidate(original_facts)
    print(f"✓ Consolidation complete")
    print(f"  Duplicates removed: {merge_result['duplicate_count']}")
    print(f"  Compression: {merge_result['compression_ratio']:.2f}x")
    print()

    # Step 3: Check quality
    print("Step 3: Checking fact retention...")
    print("-" * 70)
    quality_results = checker.check_fact_retention(original_facts, merge_result['text'])
    by_type_results = checker.analyze_by_type(original_facts, quality_results)
    print(f"✓ Quality check complete")
    print()

    # Print report
    checker.print_report(original_facts, merge_result, quality_results, by_type_results)

    # Save results
    output_file = Path(__file__).parent.parent / "results" / "consolidation_quality_check.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w') as f:
        json.dump({
            'input': {
                'total_facts': len(original_facts),
                'facts': original_facts
            },
            'consolidation': {
                'output_text': merge_result['text'],
                'unique_facts': merge_result['num_unique_facts'],
                'duplicates_removed': merge_result['duplicate_count'],
                'compression_ratio': merge_result['compression_ratio']
            },
            'quality': {
                'recall': quality_results['recall'],
                'preserved_count': quality_results['preserved_count'],
                'lost_count': quality_results['lost_count'],
                'by_type': by_type_results
            }
        }, f, indent=2)

    print(f"✓ Results saved to {output_file}")


if __name__ == "__main__":
    main()
