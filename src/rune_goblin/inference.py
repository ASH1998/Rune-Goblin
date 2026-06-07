"""Inference: load base (+ optional LoRA adapter) and turn runes into spells.

Falls back gracefully when no model/GPU is available so the Gradio app and
the API can still run on the deterministic rule engine alone (handy for UI
development before the fine-tune finishes).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

from .engine import GameState, clamp_spell, resolve_spell
from .prompts import build_chat_messages
from .schema import FALLBACK_SPELL, SpellResult, try_parse_spell


class SpellModel:
    """Wraps a (base + LoRA) causal LM that emits spell JSON."""

    def __init__(self, base: str, adapter: str | None = None, max_new_tokens: int = 256):
        load_dotenv()
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        token = os.environ.get("HF_TOKEN")
        self.max_new_tokens = max_new_tokens
        self.tokenizer = AutoTokenizer.from_pretrained(base, trust_remote_code=True, token=token)
        dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
        self.model = AutoModelForCausalLM.from_pretrained(
            base, trust_remote_code=True, token=token, torch_dtype=dtype,
            device_map="auto" if torch.cuda.is_available() else None,
        )
        if adapter and Path(adapter).exists():
            from peft import PeftModel

            self.model = PeftModel.from_pretrained(self.model, adapter)
        self.model.eval()

    def _generate(self, messages: list[dict]) -> str:
        import torch

        enc = self.tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, return_tensors="pt", return_dict=True,
        )
        enc = {k: v.to(self.model.device) for k, v in enc.items()}
        input_len = enc["input_ids"].shape[1]
        with torch.no_grad():
            out = self.model.generate(
                **enc,
                max_new_tokens=self.max_new_tokens,
                do_sample=True,
                temperature=0.7,
                top_p=0.9,
                pad_token_id=self.tokenizer.pad_token_id or self.tokenizer.eos_token_id,
            )
        text = self.tokenizer.decode(out[0][input_len:], skip_special_tokens=True)
        return text

    def cast(self, state: GameState, runes: list[str]) -> SpellResult:
        """Generate a spell, repair/validate JSON, then clamp to safe HP ranges."""
        messages = build_chat_messages(state, runes)
        # one retry on invalid JSON (Risk 2)
        for _ in range(2):
            raw = self._generate(messages)
            spell = try_parse_spell(raw)
            if spell is not None:
                return clamp_spell(spell, state)
        return clamp_spell(FALLBACK_SPELL.model_copy(), state)


@lru_cache(maxsize=1)
def get_model(base: str | None = None, adapter: str | None = None) -> SpellModel | None:
    """Lazily construct the model; return ``None`` if it can't be loaded."""
    base = base or os.environ.get("RG_BASE_MODEL", "models/MiniCPM5-1B-SFT")
    adapter = adapter or os.environ.get("RG_ADAPTER", "models/rune-goblin-lora")
    try:
        return SpellModel(base, adapter if adapter and Path(adapter).exists() else None)
    except Exception as exc:  # noqa: BLE001 - want any failure to degrade gracefully
        print(f"[inference] model unavailable, using rule engine fallback: {exc}")
        return None


def cast_spell(state: GameState, runes: list[str], use_model: bool = True) -> SpellResult:
    """Top-level entry: try the fine-tuned model, else the rule engine."""
    if use_model:
        model = get_model()
        if model is not None:
            return model.cast(state, runes)
    return resolve_spell(state, runes)
