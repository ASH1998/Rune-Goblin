"""Rune Goblin — a fine-tuned spell-language dungeon game.

Public surface used by the UIs and scripts.
"""

from .engine import GameState, clamp_spell, resolve_spell
from .game import Game
from .schema import SpellResult, VisionSpellResult, try_parse_spell, try_parse_vision_spell

__all__ = [
    "Game",
    "GameState",
    "SpellResult",
    "VisionSpellResult",
    "resolve_spell",
    "clamp_spell",
    "try_parse_spell",
    "try_parse_vision_spell",
]

__version__ = "0.1.0"
