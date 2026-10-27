"""Réentraîne le classifieur avec les corrections des étudiants (boucle de feedback, module 5).

Les corrections sont enregistrées par le service dans data/classification/feedback.csv
(route POST /classify/feedback, appelée par PHP quand un étudiant change la catégorie
d'un cours). Ce script :
  1. ajoute ces textes corrigés aux données d'entraînement ;
  2. réentraîne le MÊME pipeline avec les MÊMES hyperparamètres que le modèle actuel ;
  3. compare l'ancien et le nouveau modèle sur le test réel (F1 macro) ;
  4. ne remplace le modèle que si le nouveau est strictement meilleur (l'ancien est archivé).

Usage : python scripts/retrain_with_feedback.py [--dry-run]
Le service IA doit être redémarré pour charger le nouveau modèle.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import joblib
from sklearn.base import clone
from sklearn.metrics import f1_score

SERVICE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_DIR))

from app.config import load_categories  # noqa: E402

DATA = SERVICE_DIR / "data" / "classification"
MODEL = SERVICE_DIR / "models" / "classifier.joblib"


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def f1_on(pipeline, rows: list[dict], labels: list[str]) -> float:
    predictions = pipeline.predict([r["text"] for r in rows])
    return float(f1_score([r["label"] for r in rows], predictions, labels=labels, average="macro", zero_division=0))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="compare sans remplacer le modèle")
    args = parser.parse_args()

    categories = load_categories()
    feedback = [r for r in read_csv(DATA / "feedback.csv") if r.get("label") in categories and r.get("text")]
    # Un même cours corrigé plusieurs fois ne doit compter qu'une fois (dernière correction gagnante).
    feedback = list({r["text"]: r for r in feedback}.values())
    if not feedback:
        print("Aucune correction d'étudiant à intégrer (data/classification/feedback.csv vide ou absent).")
        return
    train = read_csv(DATA / "train.csv")
    test = read_csv(DATA / "test_reel.csv")
    test_texts = {r["text"] for r in test}
    feedback = [r for r in feedback if r["text"] not in test_texts]  # jamais de fuite vers le test
    labels = sorted({r["label"] for r in test}, key=categories.index)

    bundle = joblib.load(MODEL)
    old = bundle["pipeline"]
    new = clone(old)
    texts = [r["text"] for r in train] + [r["text"] for r in feedback]
    targets = [r["label"] for r in train] + [r["label"] for r in feedback]
    new.fit(texts, targets)

    old_f1, new_f1 = f1_on(old, test, labels), f1_on(new, test, labels)
    result = {"corrections_ajoutees": len(feedback), "f1_macro_ancien": round(old_f1, 4),
              "f1_macro_nouveau": round(new_f1, 4), "remplace": False}
    if new_f1 > old_f1 and not args.dry_run:
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        shutil.copy(MODEL, MODEL.with_name(f"classifier-{bundle['meta'].get('version', 'ancien')}.joblib"))
        meta = {**bundle["meta"], "version": stamp, "parent": bundle["meta"].get("version"),
                "corrections_integrees": len(feedback),
                "metriques": {**bundle["meta"].get("metriques", {}), "test_reel_f1_macro": round(new_f1, 4)}}
        joblib.dump({"pipeline": new, "categories": categories, "meta": meta}, MODEL, compress=3)
        (MODEL.parent / "classifier_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                                           encoding="utf-8")
        result["remplace"] = True
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["remplace"]:
        print("Modèle conservé : le nouveau modèle n'est pas meilleur sur le test réel.")


if __name__ == "__main__":
    main()
