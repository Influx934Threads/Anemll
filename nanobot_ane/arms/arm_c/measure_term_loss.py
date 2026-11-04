#!/usr/bin/env python3
"""
Measure key term loss through the full compression pipeline.

Tests the complete flow:
  Original messages → Fact extraction → Mechanical merge → Final output

Identifies which key terms from the original conversation are missing
in the final consolidated output.
"""
import sys
import json
import re
from pathlib import Path
from typing import List, Dict, Set, Tuple
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mechanical_merger import MechanicalMerger
from structured_extractor import StructuredFactExtractor


class TermLossAnalyzer:
    """Analyze term loss through compression pipeline"""

    def __init__(self, model_path: str):
        self.extractor = StructuredFactExtractor(model_path)
        self.merger = MechanicalMerger(similarity_threshold=0.85)

        # Common words to ignore (stop words)
        self.stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'up', 'about', 'into', 'through', 'during',
            'before', 'after', 'above', 'below', 'between', 'under', 'again',
            'further', 'then', 'once', 'here', 'there', 'when', 'where', 'why',
            'how', 'all', 'both', 'each', 'few', 'more', 'most', 'other', 'some',
            'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than',
            'too', 'very', 'can', 'will', 'just', 'should', 'now', 'i', 'you',
            'he', 'she', 'it', 'they', 'we', 'user', 'assistant', 'this', 'that',
            'these', 'those', 'am', 'is', 'are', 'was', 'were', 'be', 'been',
            'being', 'have', 'has', 'had', 'do', 'does', 'did', 'doing'
        }

    def extract_key_terms(self, text: str, min_length: int = 4) -> Set[str]:
        """
        Extract key terms from text.

        Returns set of significant terms (numbers, technical terms, proper nouns, etc.)
        """
        # Lowercase for matching
        text_lower = text.lower()

        # Extract all words
        words = re.findall(r'\b\w+\b', text_lower)

        key_terms = set()

        for word in words:
            # Skip stop words
            if word in self.stop_words:
                continue

            # Keep if:
            # - Long enough (technical terms)
            # - Contains numbers (versions, ports, percentages, etc.)
            # - ALL CAPS in original (acronyms, env vars)
            # - Camel/Pascal case in original (class names, etc.)

            if len(word) >= min_length:
                key_terms.add(word)
            elif re.search(r'\d', word):
                # Contains numbers (e.g., "5432", "100", "30s")
                key_terms.add(word)

        # Also extract numbers separately (they're very important)
        numbers = re.findall(r'\b\d+(?:\.\d+)?(?:%|mb|gb|ms|s|min|hr)?\b', text_lower)
        key_terms.update(numbers)

        # Extract file paths and URLs
        paths = re.findall(r'[~/][\w/.-]+', text)
        key_terms.update([p.lower() for p in paths])

        return key_terms

    def measure_pipeline_loss(
        self,
        messages: List[Dict]
    ) -> Dict:
        """
        Measure term loss through the full pipeline.

        Args:
            messages: List of conversation messages with 'role' and 'content'

        Returns:
            Analysis with original terms, preserved terms, lost terms, and stats
        """
        # Step 1: Extract original key terms
        original_text = "\n".join([msg['content'] for msg in messages])
        original_terms = self.extract_key_terms(original_text)

        print(f"Original conversation: {len(messages)} messages")
        print(f"Original key terms: {len(original_terms)}")
        print()

        # Step 2: Extract facts from conversation
        all_facts = []
        turn_texts = []

        for i in range(0, len(messages) - 1, 2):
            if messages[i]['role'] == 'user' and messages[i+1]['role'] == 'assistant':
                turn_text = f"User: {messages[i]['content']}\nAssistant: {messages[i+1]['content']}"
                turn_texts.append(turn_text)

                facts, _ = self.extractor.extract_facts(turn_text)
                all_facts.extend(facts)

        print(f"Extracted {len(all_facts)} facts from {len(turn_texts)} turns")
        print()

        # Terms in extracted facts
        facts_text = "\n".join([f.get('content', '') for f in all_facts])
        facts_terms = self.extract_key_terms(facts_text)

        print(f"Terms in facts: {len(facts_terms)}")
        print()

        # Step 3: Mechanical merge
        merge_result = self.merger.merge(all_facts)
        consolidated_text = merge_result['text']

        # Terms in consolidated output
        consolidated_terms = self.extract_key_terms(consolidated_text)

        print(f"Terms in consolidated output: {len(consolidated_terms)}")
        print()

        # Step 4: Analyze loss at each stage
        lost_in_extraction = original_terms - facts_terms
        lost_in_merge = facts_terms - consolidated_terms
        total_lost = original_terms - consolidated_terms
        preserved = original_terms & consolidated_terms

        # Categorize lost terms
        lost_numbers = {t for t in total_lost if re.search(r'\d', t)}
        lost_paths = {t for t in total_lost if t.startswith('/') or t.startswith('~')}
        lost_technical = total_lost - lost_numbers - lost_paths

        return {
            'original': {
                'text': original_text,
                'terms': original_terms,
                'count': len(original_terms)
            },
            'facts': {
                'facts': all_facts,
                'text': facts_text,
                'terms': facts_terms,
                'count': len(facts_terms)
            },
            'consolidated': {
                'text': consolidated_text,
                'terms': consolidated_terms,
                'count': len(consolidated_terms)
            },
            'loss_analysis': {
                'lost_in_extraction': {
                    'terms': lost_in_extraction,
                    'count': len(lost_in_extraction)
                },
                'lost_in_merge': {
                    'terms': lost_in_merge,
                    'count': len(lost_in_merge)
                },
                'total_lost': {
                    'terms': total_lost,
                    'count': len(total_lost)
                },
                'preserved': {
                    'terms': preserved,
                    'count': len(preserved)
                },
                'by_category': {
                    'numbers': {
                        'terms': lost_numbers,
                        'count': len(lost_numbers)
                    },
                    'paths': {
                        'terms': lost_paths,
                        'count': len(lost_paths)
                    },
                    'technical': {
                        'terms': lost_technical,
                        'count': len(lost_technical)
                    }
                }
            },
            'metrics': {
                'extraction_retention': len(facts_terms) / len(original_terms) if original_terms else 0,
                'merge_retention': len(consolidated_terms) / len(facts_terms) if facts_terms else 0,
                'total_retention': len(preserved) / len(original_terms) if original_terms else 0
            }
        }

    def print_report(self, analysis: Dict):
        """Print detailed term loss report"""
        print("=" * 70)
        print("TERM LOSS ANALYSIS REPORT")
        print("=" * 70)
        print()

        # Pipeline stats
        print("PIPELINE STATISTICS:")
        print("-" * 70)
        print(f"Original terms:      {analysis['original']['count']}")
        print(f"After extraction:    {analysis['facts']['count']} "
              f"({analysis['metrics']['extraction_retention']:.1%} retained)")
        print(f"After merge:         {analysis['consolidated']['count']} "
              f"({analysis['metrics']['merge_retention']:.1%} from facts)")
        print(f"Total retention:     {analysis['metrics']['total_retention']:.1%}")
        print()

        # Loss breakdown
        loss = analysis['loss_analysis']
        print("LOSS BREAKDOWN:")
        print("-" * 70)
        print(f"Lost in extraction:  {loss['lost_in_extraction']['count']} terms")
        print(f"Lost in merge:       {loss['lost_in_merge']['count']} terms")
        print(f"Total lost:          {loss['total_lost']['count']} terms")
        print()

        # Lost by category
        print("LOST TERMS BY CATEGORY:")
        print("-" * 70)
        by_cat = loss['by_category']
        print(f"Numbers/metrics:     {by_cat['numbers']['count']}")
        print(f"File paths:          {by_cat['paths']['count']}")
        print(f"Technical terms:     {by_cat['technical']['count']}")
        print()

        # Show critical lost terms (numbers and paths)
        if by_cat['numbers']['terms']:
            print("⚠️  LOST NUMBERS/METRICS:")
            print("-" * 70)
            for term in sorted(by_cat['numbers']['terms'])[:20]:
                print(f"  - {term}")
            if len(by_cat['numbers']['terms']) > 20:
                print(f"  ... and {len(by_cat['numbers']['terms']) - 20} more")
            print()

        if by_cat['paths']['terms']:
            print("⚠️  LOST FILE PATHS:")
            print("-" * 70)
            for term in sorted(by_cat['paths']['terms'])[:10]:
                print(f"  - {term}")
            if len(by_cat['paths']['terms']) > 10:
                print(f"  ... and {len(by_cat['paths']['terms']) - 10} more")
            print()

        # Show sample of lost technical terms
        if by_cat['technical']['terms']:
            print("LOST TECHNICAL TERMS (sample):")
            print("-" * 70)
            for term in sorted(by_cat['technical']['terms'])[:20]:
                print(f"  - {term}")
            if len(by_cat['technical']['terms']) > 20:
                print(f"  ... and {len(by_cat['technical']['terms']) - 20} more")
            print()

        # Consolidated output
        print("CONSOLIDATED OUTPUT:")
        print("-" * 70)
        print(analysis['consolidated']['text'][:1000])
        if len(analysis['consolidated']['text']) > 1000:
            print(f"\n... ({len(analysis['consolidated']['text']) - 1000} more chars)")
        print("-" * 70)
        print()

        # Assessment
        print("=" * 70)
        print("ASSESSMENT:")
        print("=" * 70)
        retention = analysis['metrics']['total_retention']
        num_lost = by_cat['numbers']['count']

        if retention >= 0.90 and num_lost == 0:
            print("✅ EXCELLENT - >90% retention, no numbers lost")
        elif retention >= 0.80 and num_lost <= 2:
            print("✓ GOOD - >80% retention, minimal number loss")
        elif retention >= 0.70 or num_lost <= 5:
            print("~ ACCEPTABLE - >70% retention or <5 numbers lost")
        else:
            print("⚠️  NEEDS IMPROVEMENT - Significant term loss detected")
            print()
            print("Recommendations:")
            if loss['lost_in_extraction']['count'] > loss['lost_in_merge']['count']:
                print("  - Extraction is the main bottleneck")
                print("  - Consider improving fact extraction prompts")
                print("  - Emphasize preserving specific numbers and paths")
            else:
                print("  - Merge is losing terms")
                print("  - Consider lower similarity threshold")
                print("  - Check if deduplication is too aggressive")
        print()


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Measure key term loss through compression pipeline"
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
    parser.add_argument(
        "--output",
        type=str,
        help="Save detailed results to JSON file"
    )

    args = parser.parse_args()

    print("=" * 70)
    print("KEY TERM LOSS ANALYSIS")
    print("=" * 70)
    print()

    # Load conversation
    if args.sample or not args.conversation:
        print("Using sample conversation")
        messages = [
            {"role": "user", "content": "Set the API rate limit to 100 requests per minute"},
            {"role": "assistant", "content": "I've set the API rate limit to 100 requests per minute. The change has been applied."},
            {"role": "user", "content": "Configure timeout to 30 seconds"},
            {"role": "assistant", "content": "Done. Timeout configured to 30 seconds."},
            {"role": "user", "content": "Set log level to debug"},
            {"role": "assistant", "content": "Log level set to debug mode."},
            {"role": "user", "content": "Connect to PostgreSQL on port 5432"},
            {"role": "assistant", "content": "Connected to PostgreSQL database on port 5432."},
            {"role": "user", "content": "Set cache size to 1024 MB"},
            {"role": "assistant", "content": "Cache size set to 1024 MB."},
        ]
    else:
        print(f"Loading conversation from: {args.conversation}")
        with open(args.conversation, 'r') as f:
            data = json.load(f)
            messages = data if isinstance(data, list) else data.get('messages', [])

    print(f"Loaded {len(messages)} messages")
    print()

    # Initialize analyzer
    print(f"Loading model: {args.model}")
    analyzer = TermLossAnalyzer(args.model)
    print()

    # Run analysis
    print("Analyzing term loss through pipeline...")
    print("-" * 70)
    analysis = analyzer.measure_pipeline_loss(messages)
    print()

    # Print report
    analyzer.print_report(analysis)

    # Save results
    if args.output:
        output_path = Path(args.output)
        # Convert sets to lists for JSON serialization
        def convert_sets(obj):
            if isinstance(obj, set):
                return sorted(list(obj))
            elif isinstance(obj, dict):
                return {k: convert_sets(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_sets(item) for item in obj]
            return obj

        with open(output_path, 'w') as f:
            json.dump(convert_sets(analysis), f, indent=2)
        print(f"✓ Detailed results saved to {output_path}")


if __name__ == "__main__":
    main()
