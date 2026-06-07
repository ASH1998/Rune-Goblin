"""5-room dungeon run: turn-based game state machine (sections 6 & 10).

Pure game logic with no UI dependency, so both the Gradio app and the
FastAPI backend drive the exact same rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .engine import GameState
from .inference import cast_spell
from .runelang import ENEMIES, ROOMS
from .schema import SpellResult, VisionSpellResult
from .vision_inference import cast_vision_spell


@dataclass
class Game:
    state: GameState = field(default_factory=GameState)
    room_index: int = 0
    log: list[str] = field(default_factory=list)
    score: int = 0
    over: bool = False
    won: bool = False
    use_model: bool = True

    @classmethod
    def new(cls, use_model: bool = True) -> Game:
        g = cls(use_model=use_model)
        g._enter_room(0)
        g.log.append("You descend into the dungeon. Draw bad spells. Suffer beautifully.")
        return g

    # -- room / enemy setup -------------------------------------------------
    def _enter_room(self, idx: int) -> None:
        room = ROOMS[idx]
        enemy = ENEMIES[room.enemy]
        self.room_index = idx
        self.state.enemy_name = enemy.name
        self.state.enemy_hp = enemy.max_hp
        self.state.enemy_max_hp = enemy.max_hp
        self.state.room_mood = enemy.mood
        self.log.append(f"— Room {idx + 1}: {room.name} — {room.intro}")
        self.log.append(f"{enemy.name} appears (HP {enemy.max_hp}, weak to {'/'.join(enemy.weakness)}).")

    @property
    def current_room(self):
        return ROOMS[self.room_index]

    # -- the turn -----------------------------------------------------------
    def cast(self, runes: list[str]) -> SpellResult:
        """Resolve a player's spell and advance the game state."""
        if self.over:
            return SpellResult(spell_name="Nothing", effect="The run is already over.")

        spell = cast_spell(self.state, runes, use_model=self.use_model)

        # apply deltas
        self.state.enemy_hp = max(0, min(self.state.enemy_max_hp, self.state.enemy_hp + spell.enemy_hp_delta))
        self.state.player_hp = max(0, min(self.state.player_max_hp, self.state.player_hp + spell.player_hp_delta))

        self.log.append(
            f"You cast {spell.spell_name} [{', '.join(runes)}]: {spell.effect}"
        )
        if spell.side_effect:
            self.log.append(f"  Side effect: {spell.side_effect}")

        self.score += max(0, -spell.enemy_hp_delta) * 10 + spell.chaos

        self._resolve_turn_end(spell)
        return spell

    def cast_drawing(self, image: Any) -> VisionSpellResult:
        """Resolve a hand-drawn canvas through the vision model."""
        if self.over:
            return VisionSpellResult(
                spell=SpellResult(spell_name="Nothing", effect="The run is already over.")
            )

        result = cast_vision_spell(
            self.state,
            image,
            room_name=self.current_room.name,
            use_model=self.use_model,
        )
        spell = result.spell
        runes = result.visual_reading.detected_runes

        self.state.enemy_hp = max(
            0, min(self.state.enemy_max_hp, self.state.enemy_hp + spell.enemy_hp_delta)
        )
        self.state.player_hp = max(
            0, min(self.state.player_max_hp, self.state.player_hp + spell.player_hp_delta)
        )

        rune_text = ", ".join(runes) if runes else "unreadable runes"
        confidence = result.visual_reading.confidence
        self.log.append(
            f"You draw {rune_text} ({confidence:.0%} confidence): {spell.spell_name}. "
            f"{spell.effect}"
        )
        if result.visual_reading.ambiguous_runes:
            self.log.append(
                f"  Ambiguous: {', '.join(result.visual_reading.ambiguous_runes)}"
            )
        if spell.side_effect:
            self.log.append(f"  Side effect: {spell.side_effect}")

        self.score += max(0, -spell.enemy_hp_delta) * 10 + spell.chaos

        self._resolve_turn_end(spell)
        return result

    def _resolve_turn_end(self, spell: SpellResult) -> None:
        # enemy defeated?
        if self.state.enemy_hp <= 0:
            self.log.append(f"{self.state.enemy_name} is defeated!")
            self.score += 50
            if self.room_index + 1 >= len(ROOMS):
                self.over = True
                self.won = True
                self.log.append(f"You survived all {len(ROOMS)} rooms! Final score: {self.score}.")
            else:
                self._enter_room(self.room_index + 1)
            return

        # enemy retaliates (simple: confused/soothed/bound enemies skip turn)
        skip = {"enemy_confused", "enemy_soothed", "enemy_bound"} & set(spell.status_effects)
        if skip:
            self.log.append(f"{self.state.enemy_name} is {'/'.join(skip)} and fumbles its turn.")
            return

        dmg = 1 + (self.room_index // 2)
        if "player_shielded" in spell.status_effects:
            self.log.append(f"Your shield absorbs the {self.state.enemy_name}'s {dmg} damage.")
            dmg = 0
        self.state.player_hp = max(0, self.state.player_hp - dmg)
        if dmg:
            self.log.append(f"{self.state.enemy_name} strikes back for {dmg} damage.")
        if self.state.player_hp <= 0:
            self.over = True
            self.won = False
            self.log.append(f"You collapse in the {self.current_room.name}. Final score: {self.score}.")

    # -- serialization for UIs ---------------------------------------------
    def snapshot(self) -> dict:
        room = self.current_room
        from .runelang import GLYPHS

        return {
            "room": {"index": self.room_index, "name": room.name, "intro": room.intro,
                     "total": len(ROOMS)},
            "enemy": {"name": self.state.enemy_name, "hp": self.state.enemy_hp,
                      "max_hp": self.state.enemy_max_hp, "weakness": list(self.state.weakness),
                      "resistance": list(self.state.resistance), "mood": self.state.room_mood},
            "player": {"hp": self.state.player_hp, "max_hp": self.state.player_max_hp,
                       "inventory": list(self.state.inventory), "courage": self.state.courage},
            "runes": [{"key": k, "symbol": g.symbol, "label": g.label} for k, g in GLYPHS.items()],
            "log": self.log[-20:],
            "score": self.score,
            "over": self.over,
            "won": self.won,
        }
