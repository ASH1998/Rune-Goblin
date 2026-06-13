# Changelog

All notable changes to Rune Goblin are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-06-13

First stable release: a fine-tuned, vision-and-dialogue-driven spell-language
dungeon game with a full rule engine that runs with or without the models.

### Added
- **Mega boss encounters** with dedicated animation states (Idle, Run, Jump,
  Attack 1–4, Hurt, Death, Special) and attack mechanics.
- **Vision model integration** — `rune-goblin-v46` GGUF + mmproj for spell/scene
  understanding, with graceful CPU/GPU fallback.
- **Dialogue model integration** — MiniCPM-V-4.6 GGUF for persona-shaped NPC
  conversation, with sanitization and thinking-strip handling.
- **Quest, item, and loot systems** — deterministic quest module, combat drops,
  weapon pricing, and toll resolution wired into world state.
- **Shops and economy** — Bone Market layout, merchant transactions, and the
  Debt Receipt mechanic.
- **Weapon tempering and reforging**, plus champion-tier damage scaling.
- **World polish** — minimap, biome visuals, shrine healing, proactive story
  beats, and expanded combat feedback.
- **Drawing/sketch customization tools** for in-game canvas interactions.
- **Hugging Face Space deployment** workflow, LFS/Xet binary-asset migration,
  and runtime config.
- **`start.sh`** launcher with `--gpu` flag to offload all GGUF layers to the GPU
  (`RG_GGUF_GPU_LAYERS=-1`); defaults to CPU.
- Test coverage for quests, dialogue personas, vision cast recovery, toll
  handling, and RPG-depth systems.

### Changed
- Refactored code structure for readability and maintainability.
- Hardened vision cast recovery and flag-safety behavior.
- Updated and versioned CSS/JS and binary assets across multiple iterations.

[1.0.0]: https://github.com/ASH1998/Rune-Goblin/releases/tag/v1.0.0
