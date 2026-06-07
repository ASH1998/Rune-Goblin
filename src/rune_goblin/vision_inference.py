"""Vision inference for the hand-drawn Rune Goblin spell model.

Loads the merged MiniCPM-V fine-tune (default: ``ASHu2/goblinV1``), sends the
canvas image plus game state, then validates the nested ``visual_reading`` +
``spell`` JSON before the game engine applies it.
"""

from __future__ import annotations

import base64
import os
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .engine import GameState, clamp_spell
from .schema import FALLBACK_VISION_SPELL, VisionSpellResult, try_parse_vision_spell

_LAST_ERROR = ""
DEFAULT_GGUF_MODEL = Path("models/goblinV1-gguf/gguf/rune-goblin-v46-Q4_K_M.gguf")
DEFAULT_GGUF_MMPROJ = Path("models/goblinV1-gguf/gguf/rune-goblin-v46-mmproj-f16.gguf")

VISION_SYSTEM_PROMPT = (
    "You are Rune Goblin, a tiny vision spell engine. Read hand-drawn RuneLang glyphs "
    "from the image, infer the drawn runes, apply RuneLang combo rules and the game state, "
    "then output valid JSON only. The JSON must contain visual_reading and spell. "
    "Spells should be weird, funny, balanced, and game-safe."
)


def format_vision_user_message(state: GameState, room_name: str | None = None) -> str:
    """Build the user text prompt used by the vision fine-tune."""
    inv = ", ".join(state.inventory) if state.inventory else "empty"
    weakness = ", ".join(state.weakness) if state.weakness else "unknown"
    resistance = ", ".join(state.resistance) if state.resistance else "unknown"
    room = room_name or "Unknown Room"
    return (
        f"STATE: player_hp={state.player_hp} enemy={state.enemy_name} "
        f"enemy_hp={state.enemy_hp} weakness={weakness} resistance={resistance} "
        f"room={room} room_mood={state.room_mood} inventory=[{inv}]\n"
        "Look at the drawn RuneLang spell on the canvas and return visual_reading "
        "plus spell JSON only."
    )


class VisionSpellModel:
    """Wrap a MiniCPM-V image-text model that emits Rune Goblin spell JSON."""

    def __init__(self, model_id: str, max_new_tokens: int = 512):
        load_dotenv()
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor

        token = os.environ.get("HF_TOKEN")
        self.max_new_tokens = max_new_tokens
        self.processor = AutoProcessor.from_pretrained(
            model_id, trust_remote_code=True, token=token
        )
        dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
        device_map = "cuda" if torch.cuda.is_available() else None
        self.model = AutoModelForImageTextToText.from_pretrained(
            model_id,
            trust_remote_code=True,
            token=token,
            torch_dtype=dtype,
            device_map=device_map,
        ).eval()

    @property
    def device(self):
        return self.model.device

    def _generate(self, image: Any, user_text: str) -> str:
        import torch

        messages = [
            {"role": "system", "content": VISION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": user_text.replace("<image>", "").strip()},
                ],
            },
        ]
        inputs = self.processor.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
            downsample_mode="16x",
        ).to(self.device)
        input_len = inputs["input_ids"].shape[1]
        with torch.no_grad():
            generated = self.model.generate(
                **inputs,
                downsample_mode="16x",
                max_new_tokens=self.max_new_tokens,
            )
        return self.processor.batch_decode(
            generated[:, input_len:], skip_special_tokens=True
        )[0]

    def cast(
        self,
        state: GameState,
        image: Any,
        room_name: str | None = None,
    ) -> VisionSpellResult:
        """Generate, parse, and clamp a vision spell result."""
        global _LAST_ERROR
        prompt = format_vision_user_message(state, room_name)
        raw = ""
        for _ in range(2):
            raw = self._generate(image, prompt)
            result = try_parse_vision_spell(raw)
            if result is not None:
                _LAST_ERROR = ""
                result.spell = clamp_spell(result.spell, state)
                return result
        _LAST_ERROR = f"model returned invalid JSON: {raw[:500]}"
        fallback = FALLBACK_VISION_SPELL.model_copy(deep=True)
        fallback.visual_reading.notes = [_LAST_ERROR]
        fallback.spell = clamp_spell(fallback.spell, state)
        return fallback


class GGUFVisionSpellModel:
    """Wrap a local llama.cpp GGUF + mmproj vision model."""

    def __init__(self, model_path: str, mmproj_path: str, max_new_tokens: int = 512):
        from llama_cpp import Llama
        from llama_cpp.llama_chat_format import MTMDChatHandler

        self.max_new_tokens = max_new_tokens
        self.chat_handler = MTMDChatHandler(clip_model_path=mmproj_path)
        self.model = Llama(
            model_path=model_path,
            chat_handler=self.chat_handler,
            n_ctx=int(os.environ.get("RG_GGUF_CTX", "4096")),
            n_gpu_layers=int(os.environ.get("RG_GGUF_GPU_LAYERS", "-1")),
            verbose=os.environ.get("RG_GGUF_VERBOSE", "0") == "1",
        )

    def _image_data_uri(self, image: Any) -> str:
        if not hasattr(image, "save"):
            from PIL import Image

            image = Image.open(image)
        buf = BytesIO()
        image.convert("RGB").save(buf, format="PNG")
        encoded = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    def _generate(self, image: Any, user_text: str) -> str:
        response = self.model.create_chat_completion(
            messages=[
                {"role": "system", "content": VISION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": self._image_data_uri(image)}},
                        {"type": "text", "text": user_text.replace("<image>", "").strip()},
                    ],
                },
            ],
            response_format={"type": "json_object"},
            max_tokens=self.max_new_tokens,
            temperature=float(os.environ.get("RG_GGUF_TEMPERATURE", "0.2")),
        )
        return response["choices"][0]["message"]["content"]

    def cast(
        self,
        state: GameState,
        image: Any,
        room_name: str | None = None,
    ) -> VisionSpellResult:
        global _LAST_ERROR
        prompt = format_vision_user_message(state, room_name)
        raw = ""
        for _ in range(2):
            raw = self._generate(image, prompt)
            result = try_parse_vision_spell(raw)
            if result is not None:
                _LAST_ERROR = ""
                result.spell = clamp_spell(result.spell, state)
                return result
        _LAST_ERROR = f"gguf model returned invalid JSON: {raw[:500]}"
        fallback = FALLBACK_VISION_SPELL.model_copy(deep=True)
        fallback.visual_reading.notes = [_LAST_ERROR]
        fallback.spell = clamp_spell(fallback.spell, state)
        return fallback


def default_vision_model_id() -> str:
    if DEFAULT_GGUF_MODEL.exists() and DEFAULT_GGUF_MMPROJ.exists():
        return str(DEFAULT_GGUF_MODEL)
    return "ASHu2/goblinV1"


@lru_cache(maxsize=1)
def get_vision_model(model_id: str | None = None) -> VisionSpellModel | None:
    """Lazily construct the vision model; return ``None`` on local setup failure."""
    global _LAST_ERROR
    model_id = model_id or os.environ.get("RG_VISION_MODEL", default_vision_model_id())
    if Path(model_id).exists():
        model_id = str(Path(model_id))
    try:
        if model_id.endswith(".gguf"):
            mmproj = os.environ.get("RG_VISION_MMPROJ", str(DEFAULT_GGUF_MMPROJ))
            if not Path(mmproj).exists():
                msg = f"RG_VISION_MMPROJ does not exist: {mmproj}"
                raise FileNotFoundError(msg)
            model = GGUFVisionSpellModel(model_id, mmproj)
        else:
            model = VisionSpellModel(model_id)
        _LAST_ERROR = ""
        return model
    except Exception as exc:  # noqa: BLE001 - UI should still launch
        _LAST_ERROR = f"{type(exc).__name__}: {exc}"
        print(f"[vision_inference] model unavailable: {_LAST_ERROR}")
        return None


def get_last_vision_error() -> str:
    return _LAST_ERROR


def cast_vision_spell(
    state: GameState,
    image: Any,
    room_name: str | None = None,
    use_model: bool = True,
) -> VisionSpellResult:
    """Top-level entry for canvas image -> validated spell JSON."""
    if use_model:
        model = get_vision_model()
        if model is not None:
            return model.cast(state, image, room_name)
    fallback = FALLBACK_VISION_SPELL.model_copy(deep=True)
    if _LAST_ERROR:
        fallback.visual_reading.notes = [f"vision_model_unavailable: {_LAST_ERROR}"]
    fallback.spell = clamp_spell(fallback.spell, state)
    return fallback
