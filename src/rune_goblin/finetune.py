"""LoRA / QLoRA fine-tuning of the base model on the RuneLang dataset.

Uses TRL's ``SFTTrainer`` with PEFT LoRA. Defaults are tuned for a single
16GB GPU (e.g. RTX 4070 Ti SUPER) training the 1B base. QLoRA (4-bit) is the
default to keep VRAM comfortable; pass ``--no-quant`` for plain bf16 LoRA.

Usage::

    uv run python -m rune_goblin.finetune \
        --data data/rune_spells.jsonl \
        --base models/MiniCPM5-1B-SFT \
        --out models/rune-goblin-lora
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="LoRA fine-tune for Rune Goblin.")
    ap.add_argument("--data", type=Path,
                    default=Path("data/rune_goblin_dataset/train_messages_only.jsonl"))
    ap.add_argument("--val-data", type=Path, default=None,
                    help="optional eval jsonl (auto-detects a sibling validation.jsonl "
                         "or <stem>_val.jsonl if present)")
    ap.add_argument("--base", default="models/MiniCPM5-1B-SFT",
                    help="local path or HF repo id of the base model")
    ap.add_argument("--out", type=Path, default=Path("models/rune-goblin-lora"))
    ap.add_argument("--epochs", type=float, default=3.0)
    ap.add_argument("--max-steps", type=int, default=-1,
                    help="cap training steps (>0 overrides epochs; handy for smoke tests)")
    ap.add_argument("--batch-size", type=int, default=4)
    ap.add_argument("--grad-accum", type=int, default=4)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--max-seq-len", type=int, default=1024)
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--lora-alpha", type=int, default=32)
    ap.add_argument("--lora-dropout", type=float, default=0.05)
    ap.add_argument("--no-quant", action="store_true", help="disable 4-bit QLoRA (use bf16 LoRA)")
    ap.add_argument("--seed", type=int, default=7)
    return ap.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    import torch
    from datasets import load_dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from trl import SFTConfig, SFTTrainer

    token = os.environ.get("HF_TOKEN")
    use_quant = not args.no_quant and torch.cuda.is_available()

    print(f"Base model : {args.base}")
    print(f"Dataset    : {args.data}")
    print(f"QLoRA 4-bit: {use_quant}")

    # --- dataset ---
    data_files = {"train": str(args.data)}
    val_path = args.val_data
    if val_path is None:
        for guess in (args.data.with_name(args.data.stem + "_val.jsonl"),
                      args.data.with_name("validation_messages_only.jsonl"),
                      args.data.with_name("validation.jsonl")):
            if guess.exists():
                val_path = guess
                break
    if val_path is not None:
        data_files["validation"] = str(val_path)
    ds = load_dataset("json", data_files=data_files)

    # --- tokenizer ---
    tokenizer = AutoTokenizer.from_pretrained(args.base, trust_remote_code=True, token=token)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # --- model (optionally 4-bit) ---
    model_kwargs: dict = {
        "trust_remote_code": True,
        "token": token,
        "torch_dtype": torch.bfloat16 if torch.cuda.is_available() else torch.float32,
    }
    if use_quant:
        from transformers import BitsAndBytesConfig

        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )
        model_kwargs["device_map"] = "auto"

    model = AutoModelForCausalLM.from_pretrained(args.base, **model_kwargs)
    model.config.use_cache = False

    peft_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
    )

    sft_config = SFTConfig(
        output_dir=str(args.out),
        num_train_epochs=args.epochs,
        max_steps=args.max_steps,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        max_length=args.max_seq_len,
        logging_steps=10,
        save_strategy="epoch",
        eval_strategy="epoch" if "validation" in data_files else "no",
        bf16=torch.cuda.is_available(),
        gradient_checkpointing=True,
        warmup_ratio=0.03,
        lr_scheduler_type="cosine",
        seed=args.seed,
        report_to=[],
        packing=False,
    )

    trainer = SFTTrainer(
        model=model,
        args=sft_config,
        train_dataset=ds["train"],
        eval_dataset=ds.get("validation"),
        peft_config=peft_config,
        processing_class=tokenizer,
    )

    trainer.train()
    args.out.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(args.out))
    tokenizer.save_pretrained(str(args.out))
    print(f"Saved LoRA adapter -> {args.out}")


if __name__ == "__main__":
    main()
