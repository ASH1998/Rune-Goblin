"""Prepare the Rune Goblin visual dataset for vision fine-tuning.

The provided dataset uses *relative* image paths (``images/rgv_XXXXX.jpg``) and
ships several layouts. Fine-tuning frameworks need **absolute** image paths and
a specific record shape. This script converts the provided splits into:

  * ``vision_swift_{train,val}.jsonl``  — ms-swift format
        {"messages": [...with <image>...], "images": ["/abs/path.jpg"]}
  * ``vision_sharegpt_{train,val}.jsonl`` — LLaMA-Factory ShareGPT format
        {"conversations": [{"from":"human"...},{"from":"gpt"...}],
         "images": ["/abs/path.jpg"], "system": "..."}

Usage::

    uv run python scripts/prepare_vision_dataset.py \
        --src data/rune_goblin_visual_dataset_5000/rune_goblin_visual_dataset \
        --out data/vision_prepared
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _abs_image(src_root: Path, rel: str) -> str:
    p = (src_root / rel).resolve()
    if not p.exists():
        raise FileNotFoundError(p)
    return str(p)


def convert_split(
    src_root: Path,
    messages_file: Path,
    out_swift: Path,
    out_sharegpt: Path,
    *,
    skip_missing_images: bool = False,
) -> tuple[int, list[str]]:
    n = 0
    skipped: list[str] = []
    with messages_file.open() as fin, \
         out_swift.open("w") as f_swift, \
         out_sharegpt.open("w") as f_sg:
        for line in fin:
            rec = json.loads(line)
            try:
                img = _abs_image(src_root, rec["image"])
            except FileNotFoundError:
                if not skip_missing_images:
                    raise
                skipped.append(rec["image"])
                continue
            msgs = rec["messages"]
            system = next((m["content"] for m in msgs if m["role"] == "system"), "")
            user = next(m["content"] for m in msgs if m["role"] == "user")
            assistant = next(m["content"] for m in msgs if m["role"] == "assistant")

            # ms-swift: keep role/content messages, attach images list
            f_swift.write(json.dumps({
                "messages": msgs,
                "images": [img],
            }, ensure_ascii=False) + "\n")

            # LLaMA-Factory ShareGPT: human/gpt turns + images + system
            f_sg.write(json.dumps({
                "conversations": [
                    {"from": "human", "value": user},
                    {"from": "gpt", "value": assistant},
                ],
                "system": system,
                "images": [img],
            }, ensure_ascii=False) + "\n")
            n += 1
    return n, skipped


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path,
                    default=Path("data/rune_goblin_visual_dataset_5000/rune_goblin_visual_dataset"))
    ap.add_argument("--out", type=Path, default=Path("data/vision_prepared"))
    ap.add_argument(
        "--skip-missing-images",
        action="store_true",
        help="Skip records whose image file is missing instead of failing.",
    )
    args = ap.parse_args()

    src_root = args.src.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    all_skipped: list[str] = []

    pairs = [
        ("train", src_root / "train_messages.jsonl"),
        ("val", src_root / "validation_messages.jsonl"),
    ]
    for split, msg_file in pairs:
        if not msg_file.exists():
            raise SystemExit(f"missing {msg_file}")
        n, skipped = convert_split(
            src_root, msg_file,
            args.out / f"vision_swift_{split}.jsonl",
            args.out / f"vision_sharegpt_{split}.jsonl",
            skip_missing_images=args.skip_missing_images,
        )
        all_skipped.extend(skipped)
        print(f"{split}: {n} records -> vision_swift_{split}.jsonl, vision_sharegpt_{split}.jsonl")
        if skipped:
            print(f"{split}: skipped {len(skipped)} records with missing images")
    if all_skipped:
        missing_report = args.out / "missing_images.txt"
        missing_report.write_text("\n".join(all_skipped) + "\n")
        print(f"Skipped {len(all_skipped)} total records. Missing image list: {missing_report}")
    print(f"Done. Absolute-path datasets written to {args.out}/")


if __name__ == "__main__":
    main()
