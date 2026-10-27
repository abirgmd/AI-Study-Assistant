from __future__ import annotations

import json

import pytest

from src.corpus import load_notes


def test_load_notes_accepts_list_and_wrapper(tmp_path) -> None:
    notes = [{"id": "n1", "title": "Titre", "text": "Contenu"}]

    direct = tmp_path / "direct.json"
    direct.write_text(json.dumps(notes), encoding="utf-8")
    wrapped = tmp_path / "wrapped.json"
    wrapped.write_text(json.dumps({"notes": notes}), encoding="utf-8")

    assert load_notes(direct) == notes
    assert load_notes(wrapped) == notes


def test_load_notes_rejects_empty_corpus(tmp_path) -> None:
    path = tmp_path / "notes.json"
    path.write_text(json.dumps({"notes": []}), encoding="utf-8")

    with pytest.raises(ValueError, match="non vide"):
        load_notes(path)


def test_load_notes_rejects_missing_file(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="introuvable"):
        load_notes(tmp_path / "absent.json")
