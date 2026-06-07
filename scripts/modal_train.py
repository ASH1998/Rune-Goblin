"""Optional: run LoRA fine-tuning on Modal GPUs (plan section 13).

This is a thin wrapper that ships the repo to a Modal A10G/A100 and invokes
``rune_goblin.finetune``. Requires ``pip install modal`` and ``modal token new``.
Local training on a 16GB GPU also works; this is only for scaling out.

    modal run scripts/modal_train.py --data data/rune_spells.jsonl
"""

from __future__ import annotations

import os

try:
    import modal
except ImportError:  # keep the file importable without modal installed
    modal = None  # type: ignore

if modal is not None:
    app = modal.App("rune-goblin-train")

    image = (
        modal.Image.debian_slim(python_version="3.11")
        .pip_install(
            "torch", "transformers>=4.45", "peft>=0.12", "trl>=0.11",
            "accelerate>=0.33", "bitsandbytes>=0.43", "datasets>=2.19",
            "sentencepiece", "protobuf", "huggingface-hub", "pydantic",
            "python-dotenv",
        )
        .add_local_dir("src", "/root/src")
    )

    volume = modal.Volume.from_name("rune-goblin-models", create_if_missing=True)

    @app.function(
        image=image,
        gpu="A10G",
        timeout=60 * 60 * 3,
        volumes={"/models": volume},
        secrets=[modal.Secret.from_name("huggingface")],  # provides HF_TOKEN
    )
    def train(data_bytes: bytes, base: str = "openbmb/MiniCPM5-1B-SFT") -> None:
        import sys

        sys.path.insert(0, "/root/src")
        os.makedirs("/root/data", exist_ok=True)
        with open("/root/data/rune_spells.jsonl", "wb") as f:
            f.write(data_bytes)

        sys.argv = [
            "finetune", "--data", "/root/data/rune_spells.jsonl",
            "--base", base, "--out", "/models/rune-goblin-lora",
        ]
        from rune_goblin.finetune import main

        main()
        volume.commit()

    @app.local_entrypoint()
    def main(data: str = "data/rune_spells.jsonl", base: str = "openbmb/MiniCPM5-1B-SFT") -> None:
        with open(data, "rb") as f:
            train.remote(f.read(), base=base)
