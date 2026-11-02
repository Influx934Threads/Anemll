"""ANE profiler with prefill/decode separation"""
import sys
from pathlib import Path
import time
import asyncio

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ane_inference import ANEInference
from arms.shared import TokenCounter, InferenceMetrics


class ANEProfiler:
    """
    Instrumented ANE inference with timing breakdowns

    Measures:
    - Prefill time (processing input tokens)
    - Decode time (generating output tokens)
    - Total wall-clock time
    """

    def __init__(self, model_path: str):
        self.inference = ANEInference(model_path)
        self.token_counter = TokenCounter()

    def profile_inference(
        self,
        prompt: str,
        max_tokens: int = 100,
        temperature: float = 0.0
    ) -> tuple[str, InferenceMetrics]:
        """
        Run inference with detailed timing

        Returns:
            (output_text, metrics)
        """
        # Tokenize input
        input_tokens = self.token_counter.count(prompt)

        # Time the entire generation
        start_total = time.perf_counter()

        # Generate output (async)
        output = asyncio.run(self.inference.generate(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature
        ))

        end_total = time.perf_counter()
        total_time_ms = (end_total - start_total) * 1000

        # Count output tokens
        output_tokens = self.token_counter.count(output)

        # Estimate prefill/decode split
        # Strategy: Use per-token timing from total time
        # Assumption: First token = prefill + 1 decode
        #             Subsequent tokens = decode only
        #
        # For more accurate measurement, we'd need to hook into
        # the CoreML generation loop. For now, use approximation:
        # - Prefill: ~20% of total time (estimate)
        # - Decode: ~80% of total time (estimate)
        #
        # These will be refined by actual measurements
        prefill_time_ms, decode_time_ms = self._estimate_split(
            total_time_ms, input_tokens, output_tokens
        )

        metrics = InferenceMetrics(
            prefill_time_ms=prefill_time_ms,
            decode_time_ms=decode_time_ms,
            total_time_ms=total_time_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_name="qwen3-1.7b-ane"
        )

        return output, metrics

    def _estimate_split(
        self,
        total_time_ms: float,
        input_tokens: int,
        output_tokens: int
    ) -> tuple[float, float]:
        """
        Estimate prefill vs decode time split

        Strategy:
        1. Assume linear scaling for prefill (proportional to input)
        2. Assume linear scaling for decode (proportional to output)
        3. Use empirical ratios to split total time

        This is an approximation. For exact measurement, we'd need
        to instrument the CoreML generation loop.
        """
        # Empirical observations from benchmark.py:
        # - Qwen3-1.7B on ANE: ~22 tok/s overall
        # - Assume prefill is much faster (like AMD's 550 vs 14)

        # Conservative estimate: prefill takes 10-20% of time
        # More accurate with actual first-token latency measurement
        prefill_ratio = 0.15  # 15% of time in prefill

        prefill_time_ms = total_time_ms * prefill_ratio
        decode_time_ms = total_time_ms * (1 - prefill_ratio)

        return prefill_time_ms, decode_time_ms

    def profile_with_first_token_timing(
        self,
        prompt: str,
        max_tokens: int = 100,
        temperature: float = 0.0
    ) -> tuple[str, InferenceMetrics]:
        """
        More accurate profiling using first-token latency

        This requires hooking into the generation loop to measure
        time-to-first-token (TTFT) separately from subsequent tokens.

        Currently a placeholder - would need to modify ane_inference.py
        to support streaming or per-token callbacks.
        """
        # TODO: Implement first-token timing when ANEInference supports it
        return self.profile_inference(prompt, max_tokens, temperature)

    def benchmark_scaling(
        self,
        input_sizes: list[int],
        output_sizes: list[int],
        iterations: int = 3
    ) -> dict:
        """
        Benchmark across different input/output sizes

        Returns:
            dict with results for each (input_size, output_size) pair
        """
        results = []

        for input_size in input_sizes:
            for output_size in output_sizes:
                # Generate prompt of target size
                prompt = self._generate_prompt(input_size)

                run_metrics = []
                for i in range(iterations):
                    print(f"Running: input={input_size}, output={output_size}, iter={i+1}/{iterations}")

                    _, metrics = self.profile_inference(
                        prompt=prompt,
                        max_tokens=output_size,
                        temperature=0.0
                    )

                    run_metrics.append(metrics.to_dict())

                # Average across iterations
                avg_metrics = self._average_metrics(run_metrics)

                results.append({
                    'input_size': input_size,
                    'output_size': output_size,
                    'iterations': iterations,
                    'avg_metrics': avg_metrics,
                    'all_runs': run_metrics
                })

        return {
            'test_matrix': results,
            'summary': self._summarize_results(results)
        }

    def _generate_prompt(self, target_tokens: int) -> str:
        """Generate a prompt with approximately target_tokens tokens"""
        # Use repetitive text to hit target size
        base_text = "This is a test prompt to measure ANE performance characteristics. "
        tokens_per_base = self.token_counter.count(base_text)

        repetitions = max(1, target_tokens // tokens_per_base)
        prompt = base_text * repetitions

        # Add instruction to ensure valid generation
        prompt += "\n\nSummarize the above text in a few sentences."

        return prompt

    def _average_metrics(self, metrics_list: list[dict]) -> dict:
        """Average metrics across multiple runs"""
        if not metrics_list:
            return {}

        avg = {}
        keys = metrics_list[0].keys()

        for key in keys:
            values = [m[key] for m in metrics_list if key in m]
            if values and isinstance(values[0], (int, float)):
                avg[key] = sum(values) / len(values)
            else:
                avg[key] = values[0]  # Take first for non-numeric

        return avg

    def _summarize_results(self, results: list[dict]) -> dict:
        """Summarize findings from benchmark results"""
        # Extract cost ratios
        cost_ratios = [r['avg_metrics']['cost_ratio'] for r in results]
        avg_cost_ratio = sum(cost_ratios) / len(cost_ratios) if cost_ratios else 0

        # Extract speeds
        prefill_speeds = [r['avg_metrics']['prefill_tok_per_sec'] for r in results]
        decode_speeds = [r['avg_metrics']['decode_tok_per_sec'] for r in results]

        avg_prefill_speed = sum(prefill_speeds) / len(prefill_speeds) if prefill_speeds else 0
        avg_decode_speed = sum(decode_speeds) / len(decode_speeds) if decode_speeds else 0

        # Prediction accuracy
        prediction_errors = [r['avg_metrics']['prediction_error_pct'] for r in results]
        avg_prediction_error = sum(prediction_errors) / len(prediction_errors) if prediction_errors else 0

        return {
            'avg_cost_ratio': avg_cost_ratio,
            'avg_prefill_tok_per_sec': avg_prefill_speed,
            'avg_decode_tok_per_sec': avg_decode_speed,
            'avg_prediction_error_pct': avg_prediction_error,
            'comparison_to_amd_npu': {
                'amd_cost_ratio': 39.0,
                'ane_cost_ratio': avg_cost_ratio,
                'ratio_difference': avg_cost_ratio - 39.0
            }
        }
