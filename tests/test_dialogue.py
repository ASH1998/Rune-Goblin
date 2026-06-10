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
    assert out["suggested_story_flag"] == ""  # flavor-only: model never sets flags


def test_sanitize_is_flavor_only_and_never_sets_flags():
    # Even a perfectly valid, allowlisted flag is dropped: durable story state is
    # owned by the deterministic cast engine, not the chat model.
    out = dialogue.sanitize({"suggested_story_flag": "tourist_helped"}, "tourist", ["wave"])
    assert out["suggested_story_flag"] == ""


def test_sanitize_falls_back_when_fields_missing():
    out = dialogue.sanitize({}, "cave_hermit", ["eye", "mirror"])
    assert out["npc_line"]  # fallback voice fills it
    assert "Mirror Hermit" in out["npc_line"]


def test_extract_json_repairs_wrapped_text():
    parsed = dialogue._extract_json('prefix {"npc_line": "hi"} trailing')
    assert parsed.get("npc_line") == "hi"


def test_user_payload_carries_persona_and_recent_story_events():
    persona = dialogue._persona_block("librarian", "insight")
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
        persona,
        "insight",
    )

    # the character's voice is injected so generated lines stay in-persona
    assert "Mold Librarian" in payload
    assert "Recent story events" in payload
    assert "The wet catalog was read." in payload
    assert "The sewer shortcut opened." in payload


def test_persona_block_pulls_canonical_voice():
    persona = dialogue._persona_block("toll_goblin", "coin")
    assert "Queue Goblin" in persona
    # the intent-matched canonical reaction is the strongest steer
    assert "responsible" in persona.lower()


def test_persona_block_empty_for_unknown_npc():
    assert dialogue._persona_block("not_a_real_npc", "neutral") == ""


def test_sanitize_drops_placeholder_toast():
    # small models sometimes emit "no toast yet" instead of leaving it blank
    out = dialogue.sanitize({"story_toast": "no toast yet", "npc_line": "Hello."},
                            "tourist", [])
    assert out["story_toast"] == ""
    assert out["npc_line"] == "Hello."


def test_user_payload_forbids_toast_on_plain_talk():
    persona = dialogue._persona_block("tourist", "neutral")
    talk = dialogue._user_payload("Toll Road", "talk", {"id": "tourist"},
                                  {}, {"mode": "talk", "runes": []}, persona, "neutral")
    cast = dialogue._user_payload("Toll Road", "talk", {"id": "tourist"},
                                  {}, {"mode": "cast", "runes": ["wave"]}, persona, "kind")
    assert "story_toast must be empty" in talk
    assert "story_toast must be empty" not in cast


def test_strip_thinking_keeps_answer_after_marker():
    raw = "First I reason about it.\nMore thoughts.\n</think>\n{\"npc_line\": \"Hi.\"}"
    out = dialogue._strip_thinking(raw)
    assert out == '{"npc_line": "Hi."}'
    # JSON survives the round-trip through the extractor
    assert dialogue._extract_json(out).get("npc_line") == "Hi."


def test_strip_thinking_passthrough_when_no_marker():
    assert dialogue._strip_thinking('{"npc_line": "Hi."}') == '{"npc_line": "Hi."}'


def test_generate_dialogue_fallback_without_model(monkeypatch):
    # force both backends off so we exercise the deterministic path
    monkeypatch.setenv("RG_USE_DIALOGUE_API", "0")
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
