# -*- coding: utf-8 -*-
"""Lernendes Benutzerwoerterbuch.

Einspeisung in die Transkription - gewaehlte Hybrid-Strategie:

1. Begriffe (Fachwoerter, Namen, Abkuerzungen) gehen als Hotwords bzw.
   Initial-Prompt an das Modell: Das biast den Whisper-Decoder und erhoeht
   die Trefferquote unbekannter Woerter deutlich - garantiert sie aber nicht.
2. Gelernte Korrekturen (falsch -> richtig) werden zusaetzlich als
   deterministische Post-Processing-Ersetzung angewendet: Damit ist
   garantiert, dass eine mehrfach identisch korrigierte Fehltranskription
   beim naechsten Diktat richtig ankommt, selbst wenn das Modell weiterhin
   falsch hoert. Die richtige Form wandert ausserdem in die Hotwords,
   damit das Modell sie moeglichst gleich selbst erkennt.

Lern-Logik: Korrekturen kommen aus dem Verlaufsfenster (Nutzer editiert
ein Transkript). Ein Wort-Diff extrahiert Ersetzungspaare; dieselbe
Ersetzung n-mal (Default 3, konfigurierbar) -> automatische Uebernahme.
"""

import difflib
import json
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from whisperflow.config import DICTIONARY_FILE, safe_print

# Woerter inkl. deutscher Umlaute, Apostrophe und Binnen-Bindestriche
_WORD_RE = re.compile(r"\w+(?:['’\-]\w+)*", re.UNICODE)

MAX_PROMPT_TERMS = 24      # Whisper-Promptfenster ist begrenzt (224 Tokens)
MAX_PROMPT_CHARS = 220
MAX_NGRAM = 3              # max. Phrasenlaenge fuer gelernte Ersetzungen


def _tokenize(text: str) -> List[str]:
    return _WORD_RE.findall(text)


def extract_replacements(original: str, corrected: str) -> List[Tuple[str, str]]:
    """Extrahiert Ersetzungspaare (falsch, richtig) aus einem Korrektur-Diff.

    Nur 'replace'-Bloecke bis MAX_NGRAM Woerter zaehlen als Korrektur;
    reine Einfuegungen/Loeschungen sind keine Ersetzungen.
    """
    orig_words = _tokenize(original)
    corr_words = _tokenize(corrected)
    pairs: List[Tuple[str, str]] = []
    matcher = difflib.SequenceMatcher(None, orig_words, corr_words, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "replace":
            continue
        n, m = i2 - i1, j2 - j1
        if n > MAX_NGRAM or m > MAX_NGRAM:
            continue
        if n == m:
            # 1:1-Ersetzungen einzeln zaehlen ("der Hubert" -> "der Hubertus")
            for k in range(n):
                pairs.append((orig_words[i1 + k], corr_words[j1 + k]))
        else:
            pairs.append((" ".join(orig_words[i1:i2]), " ".join(corr_words[j1:j2])))
    return pairs


def _adapt_case(matched: str, replacement: str, case_only: bool) -> str:
    """Passt die Ersetzung an die Schreibweise des Fundworts an."""
    if case_only:
        # Korrektur ist selbst eine Gross-/Kleinschreibungs-Korrektur:
        # exakt wie gespeichert ersetzen
        return replacement
    if matched.isupper() and len(matched) > 1:
        return replacement.upper()
    if matched[:1].isupper() and not replacement[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


@dataclass
class Correction:
    wrong: str                 # gespeichert in Kleinschreibung (Matching case-insensitiv)
    right: str
    source: str = "learned"    # learned | manual
    count: int = 0             # wie oft beobachtet

    @property
    def case_only(self) -> bool:
        return self.wrong.lower() == self.right.lower()


class UserDictionary:
    def __init__(self, path: Optional[Path] = None, learn_threshold: int = 3):
        self.path = Path(path) if path else DICTIONARY_FILE
        self.learn_threshold = max(1, int(learn_threshold))
        self._lock = threading.RLock()
        self.terms: List[str] = []
        self._corrections: Dict[str, Correction] = {}   # key: wrong.lower()
        self._pending: Dict[Tuple[str, str], int] = {}  # (wrong.lower(), right) -> count
        self.load()

    # -- Persistenz ---------------------------------------------------------

    def load(self):
        if not self.path.exists():
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            with self._lock:
                self.terms = [str(t) for t in data.get("terms", [])]
                self._corrections = {}
                for c in data.get("corrections", []):
                    corr = Correction(
                        wrong=str(c["wrong"]).lower(), right=str(c["right"]),
                        source=c.get("source", "learned"), count=int(c.get("count", 0)))
                    self._corrections[corr.wrong] = corr
                self._pending = {}
                for p in data.get("pending", []):
                    key = (str(p["wrong"]).lower(), str(p["right"]))
                    self._pending[key] = int(p.get("count", 1))
        except Exception as e:
            safe_print("[WOERTERBUCH] Konnte nicht geladen werden: {}".format(e))

    def save(self):
        with self._lock:
            data = {
                "terms": list(self.terms),
                "corrections": [
                    {"wrong": c.wrong, "right": c.right, "source": c.source, "count": c.count}
                    for c in self._corrections.values()
                ],
                "pending": [
                    {"wrong": w, "right": r, "count": n}
                    for (w, r), n in self._pending.items()
                ],
            }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            safe_print("[WOERTERBUCH] Konnte nicht gespeichert werden: {}".format(e))

    # -- Begriffe (manuell gepflegt) -----------------------------------------

    def add_term(self, term: str) -> bool:
        term = term.strip()
        with self._lock:
            if not term or term in self.terms:
                return False
            self.terms.append(term)
        self.save()
        return True

    def remove_term(self, term: str):
        with self._lock:
            if term in self.terms:
                self.terms.remove(term)
        self.save()

    # -- Korrekturen ---------------------------------------------------------

    def corrections(self) -> List[Correction]:
        with self._lock:
            return sorted(self._corrections.values(), key=lambda c: c.wrong)

    def add_correction(self, wrong: str, right: str, source: str = "manual",
                       count: int = 0) -> Optional[Correction]:
        wrong = wrong.strip()
        right = right.strip()
        if not wrong or not right or wrong == right:
            return None
        corr = Correction(wrong=wrong.lower(), right=right, source=source, count=count)
        with self._lock:
            self._corrections[corr.wrong] = corr
            # zugehoerige Pending-Eintraege aufraeumen
            self._pending = {k: v for k, v in self._pending.items() if k[0] != corr.wrong}
        self.save()
        return corr

    def remove_correction(self, wrong: str):
        with self._lock:
            self._corrections.pop(wrong.lower(), None)
        self.save()

    def clear(self):
        with self._lock:
            self.terms = []
            self._corrections = {}
            self._pending = {}
        self.save()

    # -- Lernen ----------------------------------------------------------------

    def observe_correction(self, original: str, corrected: str) -> List[Correction]:
        """Verarbeitet eine manuelle Korrektur; gibt neu gelernte Eintraege zurueck.

        Dieselbe Ersetzung learn_threshold-mal beobachtet -> Uebernahme ins
        Woerterbuch (inkl. der aktuellen Beobachtung).
        """
        if original.strip() == corrected.strip():
            return []
        newly_learned: List[Correction] = []
        pairs = extract_replacements(original, corrected)
        with self._lock:
            for wrong, right in pairs:
                wrong_key = wrong.lower()
                if wrong_key == right.lower() and wrong == right:
                    continue
                existing = self._corrections.get(wrong_key)
                if existing is not None:
                    if existing.right == right:
                        existing.count += 1
                    continue  # bereits gelernt (oder bewusst anders gesetzt)
                key = (wrong_key, right)
                self._pending[key] = self._pending.get(key, 0) + 1
                if self._pending[key] >= self.learn_threshold:
                    corr = Correction(wrong=wrong_key, right=right,
                                      source="learned", count=self._pending[key])
                    self._corrections[wrong_key] = corr
                    self._pending = {k: v for k, v in self._pending.items()
                                     if k[0] != wrong_key}
                    newly_learned.append(corr)
        self.save()
        for corr in newly_learned:
            safe_print("[WOERTERBUCH] Gelernt: '{}' -> '{}'".format(corr.wrong, corr.right))
        return newly_learned

    def pending_counts(self) -> Dict[Tuple[str, str], int]:
        with self._lock:
            return dict(self._pending)

    # -- Anwendung ---------------------------------------------------------------

    def apply_corrections(self, text: str) -> str:
        """Wendet alle Korrekturen wortgrenzen-genau und case-erhaltend an."""
        with self._lock:
            corrections = sorted(self._corrections.values(),
                                 key=lambda c: len(c.wrong), reverse=True)
        for corr in corrections:
            pattern = re.compile(
                r"(?<!\w)" + re.escape(corr.wrong).replace(r"\ ", r"\s+") + r"(?!\w)",
                re.IGNORECASE | re.UNICODE)
            text = pattern.sub(
                lambda m, c=corr: _adapt_case(m.group(0), c.right, c.case_only), text)
        return text

    def _bias_words(self) -> List[str]:
        """Begriffe + richtige Formen der Korrekturen, dedupliziert."""
        with self._lock:
            words = list(self.terms)
            for corr in self._corrections.values():
                if corr.right not in words:
                    words.append(corr.right)
        return words[:MAX_PROMPT_TERMS]

    def hotwords(self) -> str:
        """Hotword-String fuer faster-whisper."""
        return ", ".join(self._bias_words())

    def initial_prompt(self) -> str:
        """Initial-Prompt fuer Backends ohne Hotword-Support (begrenzte Laenge)."""
        prompt = ", ".join(self._bias_words())
        if len(prompt) > MAX_PROMPT_CHARS:
            prompt = prompt[:MAX_PROMPT_CHARS].rsplit(",", 1)[0]
        return prompt
