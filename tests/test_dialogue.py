"""Unit tests for NPC dialogue generation + sanitization (rune_goblin.dialogue)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rune_goblin import dialogue  # noqa: E402


def test_sanitize_clamps_lengths_and_filters_flag():
    raw = {
        "story_toast": "x" * 500,
        "npc_line": "y" * 500,
        "journal_entry": "z" * 500,
        "suggested_story_flag": "not_a_real_flag",
        "mood_shift": "m" * 500,
    }
    out = dialogue.sanitize(raw, "toll_goblin", ["coin"])
    assert len(out["story_toast"]) <= dialogue.MAX_TOAST
    assert len(out["npc_line"]) <= dialogue.MAX_NPC
    assert len(out["journal_entry"]) <= dialogue.MAX_JOURNAL
    assert out["suggested_story_flag"] == ""  # rejected (not allowlisted)


def test_sanitize_keeps_allowlisted_flag():
    out = dialogue.sanitize({"suggested_story_flag": "tourist_helped"}, "tourist", ["wave"])
    assert out["suggested_story_flag"] == "tourist_helped"


def test_sanitize_falls_back_when_fields_missing():
    out = dialogue.sanitize({}, "cave_hermit", ["eye", "mirror"])
    assert out["npc_line"]  # fallback voice fills it
    assert "Mirror Hermit" in out["npc_line"]


def test_extract_json_repairs_wrapped_text():
    parsed = dialogue._extract_json('prefix {"npc_line": "hi"} trailing')
    assert parsed.get("npc_line") == "hi"


def test_user_payload_carries_recent_story_events():
    payload = dialogue._user_payload(
        "Wet Library",
        "talk",
        {"id": "librarian", "name": "Mold Librarian"},
        {
            "goblin_class": "hunter",
            "recent_story_events": [
                {"kind": "flag", "text": "tourist_helped"},
                {"kind": "journal", "text": "The wet catalog was read."},
                {"kind": "shortcut", "text": "The sewer shortcut opened."},
            ],
        },
        {"runes": ["eye"]},
        ["tourist_helped"],
    )

    assert "recent_story_events" in payload
    assert "The wet catalog was read." in payload
    assert "The sewer shortcut opened." in payload


def test_generate_dialogue_fallback_without_model(monkeypatch):
    # force the model off so we exercise the deterministic path
    monkeypatch.setenv("RG_USE_DIALOGUE_MODEL", "0")
    dialogue._get_text_model.cache_clear()
    out = dialogue.generate_dialogue(
        area="Toll Road", scene="talk",
        target={"id": "toll_goblin", "name": "Queue Goblin", "type": "npc"},
        player={"goblin_class": "warrior"},
        action={"runes": ["coin"]},
    )
    assert out["source"] == "fallback"
    assert "Queue Goblin" in out["npc_line"]


def test_model_status_keys():
    s = dialogue.model_status()
    assert set(s) == {"enabled", "model_path", "last_error"}
