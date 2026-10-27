"""Outils de normalisation du texte français, partagés par les modules."""

from __future__ import annotations

import re
import unicodedata

# Mots vides français (sans accents, car appliqués après normalisation).
STOPWORDS_FR: frozenset[str] = frozenset("""
a afin ai aie aient aies ait alors as au aucun aucune aupres auquel aura aurai auraient aurais
aurait auras aurez auriez aurions aurons auront aussi autre autres aux auxquelles auxquels avaient
avais avait avant avec avez aviez avions avoir avons ayant ayez ayons bien c ca car ce ceci cela
celle celles celui cependant certain certaine certaines certains ces cet cette ceux chaque chez ci
comme comment d dans de des desquelles desquels deux doit donc dont du duquel elle elles en encore
entre est et etaient etais etait etant ete etes etiez etions etre eu eue eues eurent eus eusse
eussent eusses eussiez eussions eut eux faire fait faut fois font hors ici il ils j je jusqu l la
laquelle le lequel les lesquelles lesquels leur leurs lors lui m ma mais me meme memes mes moi mon
moins n ne ni non nos notre nous on ont ou par parce pas peu peut peuvent plus pour pourquoi puis qu
quand que quel quelle quelles quels qui quoi s sa sans se sera serai seraient serais serait seras
serez seriez serions serons seront ses si soi soient sois soit sommes son sont sous soyez soyons
suis sur t ta te tes toi ton tous tout toute toutes tres tu un une unes uns v vers voici voila vos
votre vous y quels quelles cest dun dune lors ainsi etc permet permettent utilise utilisee utilises
utilisees selon tel telle tels telles egalement souvent plusieurs
""".split())  # noqa: SIM905 - liste lisible et facile à modifier

_NON_WORD = re.compile(r"[^a-z0-9]+")


def strip_accents(text: str) -> str:
    """Retire les accents (é → e, ç → c) en conservant les autres caractères."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize(text: str) -> str:
    """Minuscules, sans accents, ponctuation remplacée par des espaces."""
    return _NON_WORD.sub(" ", strip_accents(text.lower())).strip()


def content_words(text: str, min_length: int = 3) -> list[str]:
    """Mots porteurs de sens : normalisés, sans mots vides ni nombres isolés.

    Args:
        text: Texte libre.
        min_length: Longueur minimale d'un mot conservé.

    Returns:
        Liste des mots, dans l'ordre d'apparition.
    """
    return [w for w in normalize(text).split()
            if len(w) >= min_length and w not in STOPWORDS_FR and not w.isdigit()]


def stem(word: str, length: int = 6) -> str:
    """Racine grossière (préfixe) pour rapprocher « tester », « tests », « testé »."""
    return word[:length]
