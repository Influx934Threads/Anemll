"""Output quality validation for token budget optimization"""
import re
from typing import Dict, Any, List


class OutputValidator:
    """
    Validate output quality for fact extraction

    Checks:
    1. Fact coverage - are key facts present?
    2. Hallucination - is there made-up information?
    3. Specificity - are numbers/names preserved?
    """

    def __init__(self):
        self.number_pattern = re.compile(r'\d+(?:\.\d+)?')
        self.entity_pattern = re.compile(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b')

    def validate(self, output: str, ground_truth: str) -> Dict[str, Any]:
        """
        Validate output against ground truth

        Args:
            output: Extracted facts
            ground_truth: Original turn text

        Returns:
            Validation metrics
        """
        # Extract key elements from ground truth
        gt_numbers = set(self.number_pattern.findall(ground_truth))
        gt_entities = set(self.entity_pattern.findall(ground_truth))

        # Extract from output
        out_numbers = set(self.number_pattern.findall(output))
        out_entities = set(self.entity_pattern.findall(output))

        # Calculate coverage
        number_coverage = len(gt_numbers & out_numbers) / len(gt_numbers) if gt_numbers else 1.0
        entity_coverage = len(gt_entities & out_entities) / len(gt_entities) if gt_entities else 1.0

        # Calculate hallucination (extra items not in ground truth)
        number_hallucinations = out_numbers - gt_numbers
        entity_hallucinations = out_entities - gt_entities

        hallucination_rate = (len(number_hallucinations) + len(entity_hallucinations)) / \
                             max(1, len(out_numbers) + len(out_entities))

        # Overall quality score
        quality_score = (number_coverage + entity_coverage) / 2 * (1 - hallucination_rate)

        return {
            'number_coverage': number_coverage,
            'entity_coverage': entity_coverage,
            'hallucination_rate': hallucination_rate,
            'quality_score': quality_score,
            'gt_numbers': len(gt_numbers),
            'out_numbers': len(out_numbers),
            'gt_entities': len(gt_entities),
            'out_entities': len(out_entities)
        }

    def validate_batch(self, outputs: List[str], ground_truths: List[str]) -> Dict[str, Any]:
        """
        Validate a batch of outputs

        Returns:
            Aggregated validation metrics
        """
        results = [self.validate(out, gt) for out, gt in zip(outputs, ground_truths)]

        # Average metrics
        avg_metrics = {
            'number_coverage': sum(r['number_coverage'] for r in results) / len(results),
            'entity_coverage': sum(r['entity_coverage'] for r in results) / len(results),
            'hallucination_rate': sum(r['hallucination_rate'] for r in results) / len(results),
            'quality_score': sum(r['quality_score'] for r in results) / len(results)
        }

        return avg_metrics


class FactCoverageChecker:
    """
    Check if key facts are covered in output

    More sophisticated than simple entity matching.
    """

    def __init__(self):
        self.key_patterns = {
            'configuration': r'(?:set|configure|enable|disable|change)\s+(\w+)\s+to\s+([\w\s]+)',
            'threshold': r'(?:maximum|minimum|limit)\s+(\w+)\s+(?:is|of)\s+([\d\w\s]+)',
            'requirement': r'(?:must|should|require)\s+([\w\s]+)',
            'preference': r'(?:prefer|like|want)\s+([\w\s]+)',
        }

    def extract_key_facts(self, text: str) -> Dict[str, List[str]]:
        """Extract key facts by category"""
        facts = {category: [] for category in self.key_patterns}

        for category, pattern in self.key_patterns.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                facts[category].extend(matches)

        return facts

    def check_coverage(self, output: str, ground_truth: str) -> Dict[str, Any]:
        """
        Check what percentage of key facts are covered

        Returns:
            Coverage metrics by category
        """
        gt_facts = self.extract_key_facts(ground_truth)
        out_facts = self.extract_key_facts(output)

        coverage = {}
        for category in self.key_patterns:
            gt_set = set(str(f) for f in gt_facts[category])
            out_set = set(str(f) for f in out_facts[category])

            if gt_set:
                coverage[category] = len(gt_set & out_set) / len(gt_set)
            else:
                coverage[category] = 1.0  # No facts to cover

        # Overall coverage
        coverage['overall'] = sum(coverage.values()) / len(self.key_patterns)

        return coverage
