# -*- coding: utf-8 -*-
"""Tests fuer das lernende Benutzerwoerterbuch."""

from whisperflow.dictionary import UserDictionary, extract_replacements


def _dict(tmp_path, threshold=3):
    return UserDictionary(path=tmp_path / "dict.json", learn_threshold=threshold)


# --- Diff-Extraktion ---------------------------------------------------------

def test_extract_single_word_replacement():
    pairs = extract_replacements(
        "Das Medikament heisst Aspirien und hilft",
        "Das Medikament heisst Aspirin und hilft")
    assert pairs == [("Aspirien", "Aspirin")]


def test_extract_ignores_insertions_and_deletions():
    assert extract_replacements("eins zwei drei", "eins zwei drei vier") == []
    assert extract_replacements("eins zwei drei", "eins drei") == []


def test_extract_multiword_phrase():
    pairs = extract_replacements(
        "wir nutzen kuh banetes im Cluster",
        "wir nutzen Kubernetes im Cluster")
    assert pairs == [("kuh banetes", "Kubernetes")]


def test_extract_multiple_separate_corrections():
    pairs = extract_replacements(
        "Herr Meier traf Frau Schulz",
        "Herr Mayer traf Frau Scholz")
    assert ("Meier", "Mayer") in pairs
    assert ("Schulz", "Scholz") in pairs


def test_extract_ignores_punctuation_changes():
    assert extract_replacements("Hallo Welt", "Hallo, Welt!") == []


# --- Lern-Logik (Akzeptanzkriterium: 3x identisch korrigiert) -------------------

def test_correction_learned_after_three_observations(tmp_path):
    d = _dict(tmp_path, threshold=3)
    base = "Wir besprechen {} im Meeting"
    fixed = "Wir besprechen Jira im Meeting"

    assert d.observe_correction(base.format("Schira"), fixed) == []
    assert d.observe_correction(base.format("Schira"), fixed) == []
    learned = d.observe_correction(base.format("Schira"), fixed)
    assert len(learned) == 1
    assert learned[0].wrong == "schira"
    assert learned[0].right == "Jira"

    # Beim naechsten Diktat wird ersetzt
    assert d.apply_corrections("Das Ticket in Schira ist offen") == \
        "Das Ticket in Jira ist offen"


def test_not_learned_below_threshold(tmp_path):
    d = _dict(tmp_path, threshold=3)
    d.observe_correction("Test Schira", "Test Jira")
    d.observe_correction("Test Schira", "Test Jira")
    assert d.apply_corrections("Schira") == "Schira"  # noch nicht gelernt
    assert d.corrections() == []


def test_threshold_configurable(tmp_path):
    d = _dict(tmp_path, threshold=2)
    d.observe_correction("Test Schira laeuft", "Test Jira laeuft")
    learned = d.observe_correction("Test Schira laeuft", "Test Jira laeuft")
    assert len(learned) == 1


def test_identical_text_learns_nothing(tmp_path):
    d = _dict(tmp_path)
    assert d.observe_correction("alles gut", "alles gut") == []
    assert d.pending_counts() == {}


# --- Anwendung -----------------------------------------------------------------

def test_apply_preserves_sentence_case(tmp_path):
    d = _dict(tmp_path)
    d.add_correction("schira", "jira")
    assert d.apply_corrections("Schira ist gut. Ich mag schira.") == \
        "Jira ist gut. Ich mag jira."


def test_apply_case_only_correction(tmp_path):
    d = _dict(tmp_path)
    d.add_correction("github", "GitHub")
    assert d.apply_corrections("Der Code liegt auf github.") == \
        "Der Code liegt auf GitHub."


def test_apply_respects_word_boundaries(tmp_path):
    d = _dict(tmp_path)
    d.add_correction("Bus", "Zug")
    assert d.apply_corrections("Der Bus und der Busfahrer") == \
        "Der Zug und der Busfahrer"


def test_apply_multiword_correction(tmp_path):
    d = _dict(tmp_path)
    d.add_correction("kuh banetes", "Kubernetes")
    assert d.apply_corrections("Wir deployen mit kuh banetes heute") == \
        "Wir deployen mit Kubernetes heute"


def test_apply_longest_match_first(tmp_path):
    d = _dict(tmp_path)
    d.add_correction("api", "API")
    d.add_correction("rest api", "REST-API")
    assert d.apply_corrections("die rest api ist da") == "die REST-API ist da"


# --- Manuelle Pflege ---------------------------------------------------------------

def test_manual_terms_and_corrections(tmp_path):
    d = _dict(tmp_path)
    assert d.add_term("Anamnese")
    assert not d.add_term("Anamnese")  # kein Duplikat
    d.add_correction("falsch", "richtig")
    assert "Anamnese" in d.hotwords()
    assert "richtig" in d.hotwords()

    d.remove_term("Anamnese")
    d.remove_correction("falsch")
    assert d.hotwords() == ""
    assert d.corrections() == []


def test_initial_prompt_capped(tmp_path):
    d = _dict(tmp_path)
    for i in range(60):
        d.add_term("Fachbegriff{:02d}".format(i))
    prompt = d.initial_prompt()
    assert len(prompt) <= 220


# --- Persistenz ----------------------------------------------------------------------

def test_persistence_roundtrip(tmp_path):
    d = _dict(tmp_path, threshold=3)
    d.add_term("Anamnese")
    d.add_correction("falsch", "richtig", source="manual")
    d.observe_correction("a Schira b", "a Jira b")  # pending

    d2 = _dict(tmp_path, threshold=3)
    assert d2.terms == ["Anamnese"]
    assert len(d2.corrections()) == 1
    assert d2.corrections()[0].right == "richtig"
    # Pending-Zaehler ueberleben den Neustart
    d2.observe_correction("a Schira b", "a Jira b")
    learned = d2.observe_correction("a Schira b", "a Jira b")
    assert len(learned) == 1


def test_learned_notification_only_once(tmp_path):
    d = _dict(tmp_path, threshold=2)
    d.observe_correction("x Schira y", "x Jira y")
    learned = d.observe_correction("x Schira y", "x Jira y")
    assert len(learned) == 1
    # Weitere identische Korrekturen erhoehen nur den Zaehler
    assert d.observe_correction("x Schira y", "x Jira y") == []
    assert d.corrections()[0].count >= 2
