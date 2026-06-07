"""Download the base model from Hugging Face into ``models/``.

The fine-tuning base is the plan's target text model (``openbmb/MiniCPM5-1B-SFT``),
which is a safetensors / llama-architecture model that LoRA can train. The GGUF
model named in ``.env`` (``MODEL``) is the multimodal / llama.cpp *serving* path
and cannot be LoRA-fine-tuned, so it is downloaded only on request.

Usage::

    uv run python -m rune_goblin.download_model            # base SFT model
    uv run python -m rune_goblin.download_model --gguf     # also the .env GGUF
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

# Plan's fine-tuning target (section 4 / 13.3).
BASE_MODEL = "openbmb/MiniCPM5-1B-SFT"


def download(repo_id: str, dest: Path, token: str | None) -> Path:
    from huggingface_hub import snapshot_download

    dest.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {repo_id} -> {dest} ...")
    path = snapshot_download(
        repo_id=repo_id,
        local_dir=dest,
        token=token,
        # skip the duplicate framework weights if present
        ignore_patterns=["*.pth", "*.onnx", "*.msgpack", "*.h5"],
    )
    print(f"Done: {path}")
    return Path(path)


def main() -> None:
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE_MODEL, help="base model repo to fine-tune")
    ap.add_argument("--gguf", action="store_true", help="also download the .env GGUF serving model")
    ap.add_argument("--models-dir", type=Path, default=Path("models"))
    args = ap.parse_args()

    token = os.environ.get("HF_TOKEN")
    # enable fast transfer if available
    os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")

    download(args.base, args.models_dir / args.base.split("/")[-1], token)

    if args.gguf:
        gguf_repo = os.environ.get("MODEL", "openbmb/MiniCPM-o-4_5-gguf")
        download(gguf_repo, args.models_dir / gguf_repo.split("/")[-1], token)


if __name__ == "__main__":
    main()
