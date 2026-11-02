"""Shared metrics and measurement utilities for NPU investigation"""
from dataclasses import dataclass, asdict
from typing import Any, Callable
import time
import json
from pathlib import Path

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False


@dataclass
class InferenceMetrics:
    """Granular timing and token metrics for a single inference"""
    prefill_time_ms: float
    decode_time_ms: float
    total_time_ms: float
    input_tokens: int
    output_tokens: int
    model_name: str = "qwen3-1.7b"

    @property
    def prefill_tok_per_sec(self) -> float:
        """Input tokens processed per second during prefill"""
        if self.prefill_time_ms == 0:
            return 0.0
        return (self.input_tokens / self.prefill_time_ms) * 1000

    @property
    def decode_tok_per_sec(self) -> float:
        """Output tokens generated per second during decode"""
        if self.decode_time_ms == 0:
            return 0.0
        return (self.output_tokens / self.decode_time_ms) * 1000

    @property
    def cost_ratio(self) -> float:
        """
        Output token cost relative to input token
        (prefill speed / decode speed)

        AMD NPU showed ~39x ratio (550 tok/s prefill, 14 tok/s decode)
        """
        if self.decode_tok_per_sec == 0:
            return 0.0
        return self.prefill_tok_per_sec / self.decode_tok_per_sec

    @property
    def predicted_time_ms(self) -> float:
        """
        Predict total time based on measured ratio
        Formula: (input_tokens / prefill_speed) + (output_tokens / decode_speed)
        """
        if self.prefill_tok_per_sec == 0 or self.decode_tok_per_sec == 0:
            return 0.0
        return ((self.input_tokens / self.prefill_tok_per_sec) * 1000 +
                (self.output_tokens / self.decode_tok_per_sec) * 1000)

    @property
    def prediction_error_pct(self) -> float:
        """Error percentage between predicted and actual time"""
        if self.total_time_ms == 0:
            return 0.0
        return abs(self.predicted_time_ms - self.total_time_ms) / self.total_time_ms * 100

    def to_dict(self) -> dict:
        """Convert to dictionary including computed properties"""
        result = asdict(self)
        result.update({
            'prefill_tok_per_sec': self.prefill_tok_per_sec,
            'decode_tok_per_sec': self.decode_tok_per_sec,
            'cost_ratio': self.cost_ratio,
            'predicted_time_ms': self.predicted_time_ms,
            'prediction_error_pct': self.prediction_error_pct
        })
        return result


@dataclass
class QualityMetrics:
    """Recall, precision, F1 for evaluation"""
    true_positives: int
    false_positives: int
    false_negatives: int
    label: str = ""

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary including computed properties"""
        result = asdict(self)
        result.update({
            'precision': self.precision,
            'recall': self.recall,
            'f1': self.f1
        })
        return result


@dataclass
class CostMetrics:
    """Cost analysis for comparing approaches"""
    total_output_tokens: int
    total_time_ms: float
    operation_count: int
    approach_name: str

    @property
    def avg_output_tokens(self) -> float:
        return self.total_output_tokens / self.operation_count if self.operation_count > 0 else 0.0

    @property
    def avg_time_ms(self) -> float:
        return self.total_time_ms / self.operation_count if self.operation_count > 0 else 0.0

    @property
    def tokens_per_second(self) -> float:
        if self.total_time_ms == 0:
            return 0.0
        return (self.total_output_tokens / self.total_time_ms) * 1000

    def to_dict(self) -> dict:
        result = asdict(self)
        result.update({
            'avg_output_tokens': self.avg_output_tokens,
            'avg_time_ms': self.avg_time_ms,
            'tokens_per_second': self.tokens_per_second
        })
        return result


class TokenCounter:
    """Accurate token counting using tiktoken or fallback estimation"""

    def __init__(self, model_name: str = "gpt-3.5-turbo"):
        self.model_name = model_name
        if TIKTOKEN_AVAILABLE:
            try:
                self.encoder = tiktoken.encoding_for_model(model_name)
            except KeyError:
                # Fallback to cl100k_base for unknown models
                self.encoder = tiktoken.get_encoding("cl100k_base")
        else:
            self.encoder = None

    def count(self, text: str) -> int:
        """Count tokens in text"""
        if self.encoder:
            return len(self.encoder.encode(text))
        else:
            # Fallback: rough estimation (chars / 4)
            return len(text) // 4

    def encode(self, text: str) -> list[int]:
        """Encode text to token IDs"""
        if self.encoder:
            return self.encoder.encode(text)
        else:
            raise RuntimeError("tiktoken not available, cannot encode")

    def decode(self, tokens: list[int]) -> str:
        """Decode token IDs to text"""
        if self.encoder:
            return self.encoder.decode(tokens)
        else:
            raise RuntimeError("tiktoken not available, cannot decode")


class TimingContext:
    """Context manager for precise timing"""

    def __init__(self, label: str = ""):
        self.label = label
        self.start_time = None
        self.elapsed_ms = None

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.elapsed_ms = (time.perf_counter() - self.start_time) * 1000
        return False


class ResultsLogger:
    """Logger for saving experiment results to JSON"""

    def __init__(self, results_dir: Path):
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def log(self, arm_name: str, results: dict):
        """Save results to JSON file"""
        output_file = self.results_dir / f"{arm_name}_results.json"

        # Add metadata
        results['_metadata'] = {
            'timestamp': time.time(),
            'arm': arm_name
        }

        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"Results saved to {output_file}")

    def load(self, arm_name: str) -> dict:
        """Load results from JSON file"""
        input_file = self.results_dir / f"{arm_name}_results.json"
        if not input_file.exists():
            raise FileNotFoundError(f"Results file not found: {input_file}")

        with open(input_file, 'r') as f:
            return json.load(f)


def measure_inference_simple(
    fn: Callable,
    input_text: str,
    max_tokens: int,
    token_counter: TokenCounter
) -> tuple[str, InferenceMetrics]:
    """
    Simple inference measurement (no prefill/decode separation)

    Args:
        fn: Function that takes (input_text, max_tokens) and returns output
        input_text: Input prompt
        max_tokens: Maximum output tokens
        token_counter: TokenCounter instance

    Returns:
        (output_text, metrics)
    """
    input_tokens = token_counter.count(input_text)

    with TimingContext("total") as total:
        output = fn(input_text, max_tokens=max_tokens)

    output_tokens = token_counter.count(output)

    # For simple measurement, assume 90% time in decode, 10% in prefill
    # (This is a rough approximation; ARM A will measure actual split)
    prefill_time_ms = total.elapsed_ms * 0.1
    decode_time_ms = total.elapsed_ms * 0.9

    metrics = InferenceMetrics(
        prefill_time_ms=prefill_time_ms,
        decode_time_ms=decode_time_ms,
        total_time_ms=total.elapsed_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens
    )

    return output, metrics


def calculate_recall_at_k(predicted: list, ground_truth: list, k: int) -> float:
    """
    Calculate recall@k

    Args:
        predicted: Predicted items (ordered by relevance)
        ground_truth: Ground truth relevant items
        k: Cutoff position

    Returns:
        Recall at position k
    """
    if not ground_truth:
        return 0.0

    predicted_at_k = set(predicted[:k])
    ground_truth_set = set(ground_truth)

    relevant_retrieved = len(predicted_at_k & ground_truth_set)
    return relevant_retrieved / len(ground_truth_set)


def calculate_precision_at_k(predicted: list, ground_truth: list, k: int) -> float:
    """
    Calculate precision@k

    Args:
        predicted: Predicted items (ordered by relevance)
        ground_truth: Ground truth relevant items
        k: Cutoff position

    Returns:
        Precision at position k
    """
    if k == 0:
        return 0.0

    predicted_at_k = set(predicted[:k])
    ground_truth_set = set(ground_truth)

    relevant_retrieved = len(predicted_at_k & ground_truth_set)
    return relevant_retrieved / k


def calculate_mean_average_precision(predicted: list, ground_truth: list) -> float:
    """
    Calculate Mean Average Precision (MAP)

    Args:
        predicted: Predicted items (ordered by relevance)
        ground_truth: Ground truth relevant items

    Returns:
        MAP score
    """
    if not ground_truth:
        return 0.0

    ground_truth_set = set(ground_truth)
    score = 0.0
    num_hits = 0.0

    for i, item in enumerate(predicted):
        if item in ground_truth_set:
            num_hits += 1.0
            precision_at_i = num_hits / (i + 1.0)
            score += precision_at_i

    return score / len(ground_truth_set) if ground_truth_set else 0.0
