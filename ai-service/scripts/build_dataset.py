"""Construit data/classification/train.csv à partir des paragraphes bruts générés.

Étapes (cf. prompts/dataset_generation.txt) :
  1. lecture de data/classification/raw/<categorie>.txt (un paragraphe par ligne) ;
  2. nettoyage des espaces, suppression des paragraphes de moins de 20 mots ;
  3. suppression des doublons exacts et des quasi-doublons (cosinus TF-IDF > 0,8) ;
  4. contrôle de fuite : aucun texte du test réel ne doit être (presque) identique à un texte
     d'entraînement ;
  5. écriture de train.csv (colonnes text, label, source, a_relire).

La colonne a_relire est remplie ensuite par scripts/train_classifier.py.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

SERVICE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_DIR))

from app.config import load_categories  # noqa: E402
from app.core.text import strip_accents  # noqa: E402

DATA = SERVICE_DIR / "data" / "classification"
NEAR_DUPLICATE = 0.8


def slug(category: str) -> str:
    """« Réseaux et sécurité » → « reseaux_et_securite »."""
    return strip_accents(category).lower().replace(" ", "_")


def near_duplicates(texts: list[str], others: list[str] | None = None) -> list[tuple[int, int, float]]:
    """Paires (i, j, similarité) au-dessus du seuil de quasi-doublon."""
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True).fit(texts + (others or []))
    a = vectorizer.transform(texts)
    b = vectorizer.transform(others) if others is not None else a
    sims = cosine_similarity(a, b)
    pairs = []
    for i in range(sims.shape[0]):
        for j in range(sims.shape[1]):
            if (others is not None or j > i) and sims[i, j] > NEAR_DUPLICATE:
                pairs.append((i, j, float(sims[i, j])))
    return pairs


def main() -> None:
    rows: list[dict] = []
    report: dict = {"par_categorie": {}, "trop_courts": 0, "doublons_exacts": 0, "quasi_doublons": []}
    seen: set[str] = set()
    for category in load_categories():
        path = DATA / "raw" / f"{slug(category)}.txt"
        lines = [" ".join(line.split()) for line in path.read_text(encoding="utf-8").splitlines()]
        kept = 0
        for text in lines:
            if not text:
                continue
            if len(text.split()) < 20:
                report["trop_courts"] += 1
                continue
            if text.lower() in seen:
                report["doublons_exacts"] += 1
                continue
            seen.add(text.lower())
            rows.append({"text": text, "label": category, "source": "synthetique", "a_relire": ""})
            kept += 1
        report["par_categorie"][category] = kept

    texts = [r["text"] for r in rows]
    to_drop = set()
    for i, j, sim in near_duplicates(texts):
        report["quasi_doublons"].append({"a": texts[i][:80], "b": texts[j][:80], "similarite": round(sim, 3)})
        to_drop.add(j)
    rows = [r for k, r in enumerate(rows) if k not in to_drop]

    test_path = DATA / "test_reel.csv"
    if test_path.exists():
        with test_path.open(encoding="utf-8") as handle:
            test_texts = [r["text"] for r in csv.DictReader(handle)]
        leaks = near_duplicates([r["text"] for r in rows], test_texts)
        report["fuites_vers_test_reel"] = len(leaks)
        if leaks:
            raise SystemExit(f"Fuite détectée : {len(leaks)} textes d'entraînement presque identiques au test réel.")

    with (DATA / "train.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["text", "label", "source", "a_relire"])
        writer.writeheader()
        writer.writerows(rows)
    report["total"] = len(rows)
    (SERVICE_DIR / "reports" / "classification").mkdir(parents=True, exist_ok=True)
    (SERVICE_DIR / "reports" / "classification" / "construction_dataset.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "quasi_doublons"}, ensure_ascii=False, indent=2))
    print(f"Quasi-doublons supprimés : {len(to_drop)}")


if __name__ == "__main__":
    main()
