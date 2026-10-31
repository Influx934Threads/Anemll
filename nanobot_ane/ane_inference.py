"""
ANE Inference - Actual model inference on Apple Neural Engine

Uses ANEMLL infrastructure to run inference on Qwen3 models.
Leverages the existing chat.py patterns from ANEMLL for proper ANE inference.
"""

import asyncio
import logging
import glob
from pathlib import Path
from typing import Optional
import sys

import torch
import torch.nn.functional as F
import numpy as np

logger = logging.getLogger(__name__)


def make_causal_mask(context_length: int, start_pos: int = 0) -> np.ndarray:
    """Create causal attention mask using numpy broadcasting (O(n) not O(n²))."""
    # Create row and column indices
    rows = np.arange(context_length).reshape(-1, 1)
    cols = np.arange(context_length).reshape(1, -1)
    # Mask where column > row (future positions)
    mask = np.where(cols > rows, -np.inf, 0.0).astype(np.float16)
    return mask.reshape(1, 1, context_length, context_length)


class ANEInference:
    """
    Inference engine running on Apple Neural Engine via ANEMLL.

    Wraps the ANEMLL model loading and inference logic for use
    in the compression service. Uses the same patterns as ANEMLL's
    chat.py for proper ANE execution.
    """

    def __init__(self, model_path: str | Path):
        self.model_path = Path(model_path).expanduser()
        self.meta_path = self.model_path / "meta.yaml"

        # Model components
        self.embed_model = None
        self.ffn_models = None
        self.lmhead_model = None
        self.tokenizer = None
        self.metadata = None
        self.state = None
        self.causal_mask = None

        # Model parameters (from metadata)
        self.context_length = 2048
        self.batch_size = 64

        self._loaded = False

    async def load(self):
        """Load model components on ANE"""
        if self._loaded:
            return

        logger.info(f"Loading ANE model from {self.model_path}")

        # Run blocking load in executor
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._load_sync)

        self._loaded = True
        logger.info("ANE model loaded successfully")

    def _load_model(self, path: Path, function_name: str | None = None):
        """Load a CoreML model following ANEMLL patterns."""
        import coremltools as ct

        compute_unit = ct.ComputeUnit.CPU_AND_NE

        if path.suffix == '.mlmodelc':
            if function_name:
                try:
                    return ct.models.CompiledMLModel(
                        str(path), compute_unit, function_name=function_name
                    )
                except RuntimeError:
                    # Fall back to mlpackage for multi-function models
                    mlpackage_path = path.with_suffix('.mlpackage')
                    if mlpackage_path.exists():
                        return ct.models.MLModel(
                            str(mlpackage_path), function_name=function_name
                        )
                    raise
            else:
                return ct.models.CompiledMLModel(str(path), compute_unit)
        else:
            if function_name:
                return ct.models.MLModel(str(path), function_name=function_name)
            else:
                return ct.models.MLModel(str(path))

    def _load_sync(self):
        """Synchronous model loading (runs in executor)"""
        import yaml
        from transformers import AutoTokenizer

        # Load metadata
        with open(self.meta_path) as f:
            self.metadata = yaml.safe_load(f)

        # Get parameters from metadata
        self.context_length = self.metadata.get('context_length', 2048)
        self.batch_size = self.metadata.get('batch_size', 64)

        logger.debug(f"Model config: context_length={self.context_length}, batch_size={self.batch_size}")

        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(str(self.model_path))

        model_dir = self.model_path

        # Load embeddings
        embed_path = self._find_model_file(model_dir, "embeddings")
        if embed_path:
            self.embed_model = self._load_model(embed_path)
            logger.debug(f"Loaded embeddings from {embed_path}")
        else:
            raise FileNotFoundError(f"No embeddings model found in {model_dir}")

        # Load LM head
        lmhead_path = self._find_model_file(model_dir, "lm_head")
        if lmhead_path:
            self.lmhead_model = self._load_model(lmhead_path)
            logger.debug(f"Loaded LM head from {lmhead_path}")
        else:
            raise FileNotFoundError(f"No LM head model found in {model_dir}")

        # Load FFN models (handles multi-function chunked models)
        self.ffn_models = self._load_ffn_models(model_dir)
        logger.debug(f"Loaded {len(self.ffn_models)} FFN model(s)")

        # Initialize state and mask
        self._init_state()

    def _find_model_file(self, model_dir: Path, component: str) -> Path | None:
        """Find model file for a component (embeddings, lm_head)."""
        patterns = [
            f"*{component}*.mlmodelc",
            f"*{component}*.mlpackage",
        ]
        for pattern in patterns:
            matches = sorted(model_dir.glob(pattern))
            if matches:
                return matches[0]
        return None

    def _load_ffn_models(self, model_dir: Path) -> list:
        """Load FFN models, handling chunked multi-function models."""
        ffn_models = []

        # Look for multi-function chunked models (prefill + infer)
        chunk_patterns = [
            "*FFN*PF*chunk*.mlmodelc",
            "*FFN*PF*chunk*.mlpackage",
        ]

        chunks = []
        for pattern in chunk_patterns:
            chunks = sorted(model_dir.glob(pattern))
            if chunks:
                break

        if chunks:
            # Multi-function model: load prefill and infer functions
            for chunk_path in chunks:
                try:
                    chunk_dict = {
                        'infer': self._load_model(chunk_path, function_name='infer'),
                        'prefill': self._load_model(chunk_path, function_name='prefill'),
                    }
                    ffn_models.append(chunk_dict)
                    logger.debug(f"Loaded FFN chunk {chunk_path.name} with prefill+infer")
                except Exception as e:
                    logger.warning(f"Failed to load multi-function FFN {chunk_path}: {e}")
                    # Fall back to single-function
                    ffn_models.append(self._load_model(chunk_path))
        else:
            # Look for single-function FFN models
            for pattern in ["*FFN*.mlmodelc", "*FFN*.mlpackage"]:
                single_ffn = sorted(model_dir.glob(pattern))
                if single_ffn:
                    for ffn_path in single_ffn:
                        ffn_models.append(self._load_model(ffn_path))
                    break

        if not ffn_models:
            raise FileNotFoundError(f"No FFN models found in {model_dir}")

        return ffn_models

    def _init_state(self):
        """Initialize model state and causal mask"""
        # Create causal mask
        self.causal_mask = torch.from_numpy(
            make_causal_mask(self.context_length)
        ).to(torch.float16)

        # Create state from FFN model
        if self.ffn_models:
            ffn_model = self.ffn_models[0]
            if isinstance(ffn_model, dict):
                self.state = ffn_model['prefill'].make_state()
            else:
                self.state = ffn_model.make_state()
            logger.debug("Created model state for KV cache")

    def reset_state(self):
        """Reset state for new generation"""
        self._init_state()

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 100,
        temperature: float = 0.7,
        stop_tokens: Optional[list[int]] = None
    ) -> str:
        """
        Generate text from a prompt using ANE.

        Args:
            prompt: Input text
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            stop_tokens: Token IDs that stop generation

        Returns:
            Generated text
        """
        if not self._loaded:
            await self.load()

        # Run generation in executor to not block event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            self._generate_sync,
            prompt,
            max_tokens,
            temperature,
            stop_tokens
        )

        return result

    def _prefill(self, input_ids: torch.Tensor) -> int:
        """Run prefill phase for prompt processing."""
        seq_len = input_ids.shape[1]
        batch_size = self.batch_size

        # Reset state for new generation
        self.reset_state()

        # Process full batches with prefill
        batch_pos = 0
        while batch_pos + batch_size <= seq_len:
            batch_end = batch_pos + batch_size
            batch_tokens = input_ids[:, batch_pos:batch_end]

            # Get embeddings
            embed_out = self.embed_model.predict({
                'input_ids': batch_tokens.numpy().astype(np.int32)
            })
            hidden_states = torch.from_numpy(embed_out['hidden_states'])

            # Position IDs - shape [batch_size], NOT [1, batch_size]
            position_ids = torch.arange(
                batch_pos, batch_pos + batch_size, dtype=torch.int32
            )

            # Get causal mask slice
            causal_mask_slice = self.causal_mask[
                :, :, batch_pos:batch_pos + batch_size, :
            ].numpy().astype(np.float16)

            # Run through FFN chunks
            for ffn_model in self.ffn_models:
                inputs = {
                    'hidden_states': hidden_states.numpy().astype(np.float16),
                    'position_ids': position_ids.numpy().astype(np.int32),
                    'causal_mask': causal_mask_slice,
                    'current_pos': np.array([batch_pos], dtype=np.int32),
                }

                if isinstance(ffn_model, dict):
                    output = ffn_model['prefill'].predict(inputs, self.state)
                else:
                    output = ffn_model.predict(inputs, self.state)

                hidden_states = torch.from_numpy(output['output_hidden_states'])

            batch_pos = batch_end

        # Process remaining tokens one-at-a-time using infer
        while batch_pos < seq_len:
            token = input_ids[:, batch_pos:batch_pos + 1]

            # Position IDs - shape [1]
            position_ids = torch.tensor([batch_pos], dtype=torch.int32)
            single_causal_mask = self.causal_mask[
                :, :, batch_pos:batch_pos + 1, :
            ].numpy().astype(np.float16)

            # Get embeddings
            embed_out = self.embed_model.predict({
                'input_ids': token.numpy().astype(np.int32)
            })
            hidden_states = torch.from_numpy(embed_out['hidden_states'])

            # Run through FFN chunks with infer
            for ffn_model in self.ffn_models:
                inputs = {
                    'hidden_states': hidden_states.numpy().astype(np.float16),
                    'position_ids': position_ids.numpy().astype(np.int32),
                    'causal_mask': single_causal_mask,
                    'current_pos': position_ids.numpy().astype(np.int32),
                }

                if isinstance(ffn_model, dict):
                    output = ffn_model['infer'].predict(inputs, self.state)
                else:
                    output = ffn_model.predict(inputs, self.state)

                hidden_states = torch.from_numpy(output['output_hidden_states'])

            batch_pos += 1

        return batch_pos

    def _generate_token(self, pos: int, token: torch.Tensor) -> torch.Tensor:
        """Generate next token logits at position pos."""
        # Get embeddings for current token
        embed_out = self.embed_model.predict({
            'input_ids': token.numpy().astype(np.int32)
        })
        hidden_states = torch.from_numpy(embed_out['hidden_states'])

        # Position and mask for single token - shape [1], NOT [1, 1]
        position_ids = torch.tensor([pos], dtype=torch.int32)
        causal_mask_slice = self.causal_mask[
            :, :, pos:pos + 1, :
        ].numpy().astype(np.float16)

        # Run through FFN chunks
        for ffn_model in self.ffn_models:
            inputs = {
                'hidden_states': hidden_states.numpy().astype(np.float16),
                'position_ids': position_ids.numpy().astype(np.int32),
                'causal_mask': causal_mask_slice,
                'current_pos': position_ids.numpy().astype(np.int32),
            }

            if isinstance(ffn_model, dict):
                output = ffn_model['infer'].predict(inputs, self.state)
            else:
                output = ffn_model.predict(inputs, self.state)

            hidden_states = torch.from_numpy(output['output_hidden_states'])

        # Get logits from LM head
        lm_out = self.lmhead_model.predict({
            'hidden_states': hidden_states.numpy().astype(np.float16)
        })

        # Handle different output formats
        if 'logits1' in lm_out:
            # Split logits format
            num_logits = self.metadata.get('split_lm_head', 8)
            logits_parts = []
            for i in range(1, num_logits + 1):
                key = f'logits{i}'
                if key in lm_out:
                    logits_parts.append(torch.from_numpy(lm_out[key]))
            logits = torch.cat(logits_parts, dim=-1)
        elif 'output_logits' in lm_out:
            logits = torch.from_numpy(lm_out['output_logits'])
        else:
            # Try first available output
            for key in lm_out:
                if 'logits' in key.lower():
                    logits = torch.from_numpy(lm_out[key])
                    break
            else:
                raise RuntimeError(f"No logits in LM head output: {list(lm_out.keys())}")

        return logits

    def _generate_sync(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        stop_tokens: Optional[list[int]]
    ) -> str:
        """Synchronous generation (runs in executor)"""

        # Tokenize
        input_ids = self.tokenizer.encode(prompt, return_tensors="pt")
        input_ids = input_ids.to(torch.int32)

        # Set default stop tokens
        if stop_tokens is None:
            stop_tokens = []
            if self.tokenizer.eos_token_id:
                stop_tokens.append(self.tokenizer.eos_token_id)
            # Qwen special tokens
            stop_tokens.extend([151645, 151643])

        # Prefill phase
        pos = self._prefill(input_ids)

        generated_tokens = []

        # Generation loop
        for _ in range(max_tokens):
            # Get current token (last generated or last from prompt)
            if generated_tokens:
                current_token = torch.tensor([[generated_tokens[-1]]], dtype=torch.int32)
            else:
                current_token = input_ids[:, -1:]

            # Generate next token
            logits = self._generate_token(pos, current_token)

            # Sample
            if temperature > 0:
                probs = F.softmax(logits[0, -1, :] / temperature, dim=-1)
                next_token_id = torch.multinomial(probs, num_samples=1).item()
            else:
                next_token_id = torch.argmax(logits[0, -1, :]).item()

            # Check stop condition
            if next_token_id in stop_tokens:
                break

            generated_tokens.append(next_token_id)
            pos += 1

            # Check context limit
            if pos >= self.context_length:
                logger.warning("Reached context length limit")
                break

        # Decode generated tokens
        output = self.tokenizer.decode(generated_tokens, skip_special_tokens=True)

        return output


class ANEInferencePool:
    """
    Pool of ANE inference instances for concurrent requests.

    Since ANE can handle multiple concurrent streams efficiently,
    this pool manages multiple inference instances.
    """

    def __init__(self, model_path: str | Path, pool_size: int = 2):
        self.model_path = Path(model_path)
        self.pool_size = pool_size
        self._instances: list[ANEInference] = []
        self._semaphore: asyncio.Semaphore | None = None
        self._current_idx = 0

    async def start(self):
        """Initialize the inference pool"""
        self._semaphore = asyncio.Semaphore(self.pool_size)

        for _ in range(self.pool_size):
            instance = ANEInference(self.model_path)
            await instance.load()
            self._instances.append(instance)

        logger.info(f"ANE inference pool started with {self.pool_size} instances")

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate using next available instance"""
        async with self._semaphore:
            instance = self._instances[self._current_idx]
            self._current_idx = (self._current_idx + 1) % self.pool_size

            return await instance.generate(prompt, **kwargs)
