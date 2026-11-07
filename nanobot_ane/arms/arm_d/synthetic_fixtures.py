"""
Synthetic nanobot conversations with planted facts.

Inspired by AMD NPU's eval_rolling.py fixture approach.
Creates deterministic, seeded conversations with known "needle" facts
for testing recall without requiring user interaction.
"""

import random
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class PlantedFact:
    """A fact we intentionally plant to test recall"""
    category: str  # 'file_path', 'config', 'error', 'decision', etc.
    text: str
    turn_index: int

    def __repr__(self):
        return f"PlantedFact({self.category}: '{self.text}' @ turn {self.turn_index})"


def generate_nanobot_conversation(
    num_turns: int,
    seed: int,
    facts_per_10_turns: int = 8
) -> Tuple[List[dict], List[PlantedFact]]:
    """
    Generate synthetic nanobot conversation with planted facts.

    Args:
        num_turns: Number of turn pairs to generate
        seed: Random seed for reproducibility
        facts_per_10_turns: How many facts to plant per 10 turns (default: 8, matching AMD)

    Returns:
        (turns, planted_facts)

        turns: [{'user': '...', 'assistant': '...'}, ...]
        planted_facts: [PlantedFact(...), ...]
    """
    random.seed(seed)

    turns = []
    planted = []

    # Templates for realistic nanobot exchanges
    coding_templates = [
        ("Help me debug this Python error:\n```python\n{code}\n```\nI'm getting: {error}",
         "Let me analyze that. The error '{error}' indicates {explanation}. Try: {solution}"),
        ("Write a function to {task}",
         "Here's an implementation:\n```python\n{code}\n```\nThis {explanation}."),
        ("Optimize this code:\n```python\n{code}\n```",
         "I can optimize it. {explanation}. Here's the improved version:\n```python\n{optimized}\n```"),
    ]

    config_templates = [
        ("Set {config_key} to {config_value}",
         "Done. Configuration updated: {config_key}={config_value}. This will {effect}."),
        ("What's the current {service} configuration?",
         "The {service} is configured with: {details}. Status: {status}."),
        ("Update {service} settings",
         "Updated {service} settings: {details}. Applied successfully."),
    ]

    file_templates = [
        ("Create a new file at {filepath} with {content_type} content",
         "Created {filepath} successfully. File contains {content_desc}."),
        ("Read the contents of {filepath}",
         "Contents of {filepath}:\n```\n{content}\n```"),
        ("Move {src_path} to {dst_path}",
         "Moved {src_path} to {dst_path}. Operation completed."),
    ]

    # Fact templates that will be planted
    fact_templates = [
        ('file_path', '/usr/local/bin/nanobot_v{version}_{seed}'),
        ('file_path', '~/.config/nanobot/settings_{seed}.yaml'),
        ('config', 'timeout={value}s'),
        ('config', 'max_retries={value}'),
        ('error', 'ConnectionError: connection refused (errno {errno})'),
        ('error', 'RuntimeError: {error_msg}'),
        ('model', 'qwen3-{size}b-v{version}'),
        ('model', 'bonsai-{size}b-pq{quant}'),
        ('decision', 'user chose option {option}'),
        ('decision', 'user enabled {feature}'),
        ('measurement', 'latency: {latency}ms'),
        ('measurement', 'throughput: {throughput} req/s'),
        ('status', 'build status: {status}'),
        ('version', 'version {major}.{minor}.{patch}'),
    ]

    # Calculate how many facts to plant
    num_facts = max(1, (num_turns // 10) * facts_per_10_turns)
    # Ensure we don't try to plant more facts than we have turns
    num_facts = min(num_facts, num_turns)
    fact_positions = sorted(random.sample(range(num_turns), num_facts))

    for i in range(num_turns):
        # Pick a random category
        category_choice = random.choice(['coding', 'config', 'file'])

        if category_choice == 'coding':
            user_tmpl, assistant_tmpl = random.choice(coding_templates)
            code_sample = f"def process_{i}():\n    return data.process()"
            user_msg = user_tmpl.format(
                code=code_sample,
                error=f"TypeError on line {random.randint(10, 50)}",
                task="process CSV data and extract key metrics"
            )
            assistant_msg = assistant_tmpl.format(
                error=f"TypeError on line {random.randint(10, 50)}",
                explanation="the data type mismatch in the input",
                solution="validate input types before processing",
                code=code_sample,
                optimized=code_sample.replace("process()", "process_fast()")
            )
        elif category_choice == 'config':
            user_tmpl, assistant_tmpl = random.choice(config_templates)
            user_msg = user_tmpl.format(
                config_key=random.choice(["timeout", "batch_size", "workers"]),
                config_value=random.randint(10, 100),
                service=random.choice(["API", "database", "cache"])
            )
            assistant_msg = assistant_tmpl.format(
                config_key=random.choice(["timeout", "batch_size"]),
                config_value=random.randint(10, 100),
                service=random.choice(["API", "database"]),
                details=f"setting={random.randint(10, 100)}",
                effect="take effect immediately",
                status="active"
            )
        else:  # file
            user_tmpl, assistant_tmpl = random.choice(file_templates)
            user_msg = user_tmpl.format(
                filepath=f"/tmp/file_{i}.txt",
                content_type=random.choice(["config", "data", "log"]),
                src_path=f"/tmp/src_{i}.txt",
                dst_path=f"/tmp/dst_{i}.txt"
            )
            assistant_msg = assistant_tmpl.format(
                filepath=f"/tmp/file_{i}.txt",
                content_desc="sample data",
                content="line 1\nline 2\nline 3",
                src_path=f"/tmp/src_{i}.txt",
                dst_path=f"/tmp/dst_{i}.txt"
            )

        # If this position should have a planted fact, inject it
        if i in fact_positions:
            fact_category, fact_template = random.choice(fact_templates)

            # Generate fact text
            fact_text = fact_template.format(
                seed=seed,
                value=random.randint(10, 120),
                errno=random.randint(10, 99),
                error_msg=f"invalid state at step {random.randint(1, 10)}",
                size=random.choice([1.7, 3, 8, 9]),
                version=f"{random.randint(1, 3)}.{random.randint(0, 9)}",
                quant=random.choice([2, 4, 6]),
                option=random.choice(['A', 'B', 'C']),
                feature=random.choice(['caching', 'logging', 'telemetry']),
                latency=random.randint(100, 2000),
                throughput=random.randint(10, 500),
                status=random.choice(['passed', 'failed', 'pending']),
                major=random.randint(1, 3),
                minor=random.randint(0, 9),
                patch=random.randint(0, 20),
            )

            # Inject fact into assistant response as an "orphaned" aside
            # This mimics AMD's finding of "context-orphaned asides" being missed
            injection_styles = [
                f"\n\nNote: {fact_text}",
                f"\n\nImportant: {fact_text}",
                f"\n\nFYI: {fact_text}",
                f"\n\n({fact_text})",
                f" Also, {fact_text}.",
            ]

            injection = random.choice(injection_styles)
            assistant_msg += injection

            planted.append(PlantedFact(
                category=fact_category,
                text=fact_text,
                turn_index=i
            ))

        turns.append({
            'user': user_msg,
            'assistant': assistant_msg
        })

    return turns, planted


def score_recall(extracted_facts: str, planted: List[PlantedFact]) -> Tuple[List[PlantedFact], List[PlantedFact]]:
    """
    Score how many planted facts were recalled in extraction.

    Args:
        extracted_facts: The complete extracted facts text
        planted: List of planted facts to check for

    Returns:
        (recalled, missed)
    """
    recalled = []
    missed = []

    for fact in planted:
        # Simple substring match - fact text should appear in extraction
        # This is conservative: the fact might be paraphrased, but we require
        # key terms to be present
        if fact.text in extracted_facts:
            recalled.append(fact)
        else:
            # Check if key components are present (for paraphrased versions)
            # Extract key numbers/identifiers from the fact
            import re
            # Find numbers in the fact
            fact_numbers = set(re.findall(r'\d+', fact.text))
            # Find key words (length >= 4, not common words)
            common_words = {'with', 'from', 'that', 'this', 'have', 'were', 'been'}
            fact_words = set(w.lower() for w in re.findall(r'\b\w{4,}\b', fact.text)
                           if w.lower() not in common_words)

            # Check if most key components are present
            if fact_numbers:
                numbers_found = sum(1 for n in fact_numbers if n in extracted_facts)
                if numbers_found / len(fact_numbers) >= 0.7:  # 70% of numbers present
                    recalled.append(fact)
                    continue

            if fact_words:
                words_found = sum(1 for w in fact_words if w in extracted_facts.lower())
                if words_found / len(fact_words) >= 0.7:  # 70% of key words present
                    recalled.append(fact)
                    continue

            missed.append(fact)

    return recalled, missed


# Test the generator
if __name__ == "__main__":
    print("Testing synthetic fixture generator...")
    print()

    turns, planted = generate_nanobot_conversation(num_turns=20, seed=101)

    print(f"Generated {len(turns)} turns with {len(planted)} planted facts")
    print()
    print("Sample turn:")
    print(f"User: {turns[0]['user'][:100]}...")
    print(f"Assistant: {turns[0]['assistant'][:100]}...")
    print()
    print("Planted facts:")
    for fact in planted[:5]:
        print(f"  {fact}")
