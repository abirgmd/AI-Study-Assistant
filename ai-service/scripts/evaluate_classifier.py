"""Évalue le modèle de classification sauvegardé sur le test réel (module 5).

Produit dans reports/classification/ :
  - rapport_par_classe.csv   précision, rappel, F1 et effectif de chaque catégorie
  - matrice_confusion.png    matrice de confusion sur le test réel
  - seuil_confiance.csv/.png part des cours classés automatiquement et exactitude parmi eux
                             selon le seuil de confiance (choix du seuil 0,5)
  - predictions_test_reel.csv prédiction, confiance et mots explicatifs pour chaque extrait
  - comparatif_modeles.png   F1 macro des candidats (validation croisée et test réel)

Usage : python scripts/evaluate_classifier.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support

SERVICE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_DIR))

from app.config import get_settings, load_categories  # noqa: E402
from app.modules.classification.classifier import UNCLASSIFIED, CourseClassifier  # noqa: E402

DATA = SERVICE_DIR / "data" / "classification"
REPORTS = SERVICE_DIR / "reports" / "classification"


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    categories = load_categories()
    try:
        override = get_settings().classifier_min_confidence
    except ValueError:  # pas de .env (jeton absent) : seuil enregistré avec le modèle
        override = None
    classifier = CourseClassifier.load(SERVICE_DIR / "models" / "classifier.joblib", override, 20_000)
    min_confidence = classifier.min_confidence
    with (DATA / "test_reel.csv").open(encoding="utf-8") as handle:
        test = list(csv.DictReader(handle))
    y_true = [r["label"] for r in test]
    predictions = [classifier.predict(r["text"]) for r in test]
    y_pred = [p.top[0]["category"] for p in predictions]  # catégorie la plus probable, avant seuil
    present = [c for c in categories if c in set(y_true)]

    precision, recall, f1, support = precision_recall_fscore_support(y_true, y_pred, labels=categories,
                                                                     zero_division=0)
    per_class = [{"categorie": c, "precision": round(float(p), 4), "rappel": round(float(r), 4),
                  "f1": round(float(f), 4), "effectif_test": int(s)}
                 for c, p, r, f, s in zip(categories, precision, recall, f1, support, strict=True)]
    write_csv(REPORTS / "rapport_par_classe.csv", per_class)

    matrix = confusion_matrix(y_true, y_pred, labels=categories)
    fig, ax = plt.subplots(figsize=(8.5, 7))
    ax.imshow(matrix, cmap="Blues")
    short = [c.replace(" et ", " & ") for c in categories]
    ax.set_xticks(range(len(categories)), short, rotation=40, ha="right", fontsize=8)
    ax.set_yticks(range(len(categories)), short, fontsize=8)
    for i in range(len(categories)):
        for j in range(len(categories)):
            if matrix[i, j]:
                ax.text(j, i, matrix[i, j], ha="center", va="center",
                        color="white" if matrix[i, j] > matrix.max() / 2 else "black")
    ax.set_xlabel("Catégorie prédite")
    ax.set_ylabel("Catégorie réelle (étiquetage manuel)")
    ax.set_title(f"Matrice de confusion — test réel ({len(test)} extraits de cours)")
    fig.tight_layout()
    fig.savefig(REPORTS / "matrice_confusion.png", dpi=130)
    plt.close(fig)

    confidences = np.array([p.confidence for p in predictions])
    correct = np.array([t == p for t, p in zip(y_true, y_pred, strict=True)])
    sweep = []
    for threshold in np.round(np.arange(0.0, 0.95, 0.05), 2):
        accepted = confidences >= threshold
        sweep.append({"seuil": float(threshold), "part_classee_automatiquement": round(float(accepted.mean()), 4),
                      "exactitude_parmi_classes": round(float(correct[accepted].mean()), 4) if accepted.any() else None,
                      "erreurs_affichees": int((accepted & ~correct).sum())})
    write_csv(REPORTS / "seuil_confiance.csv", sweep)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot([s["seuil"] for s in sweep], [s["part_classee_automatiquement"] for s in sweep], marker="o",
            label="Part des cours classés automatiquement")
    ax.plot([s["seuil"] for s in sweep], [s["exactitude_parmi_classes"] or np.nan for s in sweep], marker="s",
            label="Exactitude parmi les cours classés")
    ax.axvline(min_confidence, color="black", linestyle="--", label=f"Seuil retenu = {min_confidence}")
    ax.set_xlabel("Seuil de confiance")
    ax.set_ylim(0, 1.05)
    ax.set_title("Seuil de confiance : couverture contre exactitude (test réel)")
    ax.legend(loc="lower left")
    fig.tight_layout()
    fig.savefig(REPORTS / "seuil_confiance.png", dpi=130)
    plt.close(fig)

    write_csv(REPORTS / "predictions_test_reel.csv", [
        {"source": r["source"], "categorie_reelle": r["label"], "prediction": p.top[0]["category"],
         "confiance": p.confidence, "affiche": p.category, "correct": t == p.top[0]["category"],
         "mots_explicatifs": " ; ".join(p.explanation), "extrait": r["text"][:160]}
        for r, p, t in zip(test, predictions, y_true, strict=True)])

    accepted = confidences >= min_confidence
    summary = {
        "modele": classifier.meta.get("modele"),
        "version": classifier.meta.get("version"),
        "test_reel_extraits": len(test),
        "classes_presentes": present,
        "exactitude": round(accuracy_score(y_true, y_pred), 4),
        "f1_macro_classes_presentes": round(f1_score(y_true, y_pred, labels=present, average="macro",
                                                     zero_division=0), 4),
        "seuil": min_confidence,
        "part_classee_automatiquement": round(float(accepted.mean()), 4),
        "exactitude_parmi_classes": round(float(correct[accepted].mean()), 4) if accepted.any() else None,
        "laisses_a_classer": int((~accepted).sum()),
        "unclassified_label": UNCLASSIFIED,
    }
    (REPORTS / "evaluation_test_reel.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                                       encoding="utf-8")

    comparison_path = REPORTS / "comparatif.csv"
    if comparison_path.exists():
        with comparison_path.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        fig, ax = plt.subplots(figsize=(8, 4.2))
        x = np.arange(len(rows))
        ax.bar(x - 0.2, [float(r["cv_f1_macro"]) for r in rows], 0.4, label="Validation croisée (synthétique)")
        ax.bar(x + 0.2, [float(r["test_reel_f1_macro"]) for r in rows], 0.4, label="Test réel (vrais cours)")
        ax.set_xticks(x, [r["cle"] + (" ★" if r["retenu"] else "") for r in rows])
        ax.set_ylim(0, 1)
        ax.set_ylabel("F1 macro")
        ax.set_title("Comparaison des modèles de classification (★ = retenu)")
        ax.legend()
        fig.tight_layout()
        fig.savefig(REPORTS / "comparatif_modeles.png", dpi=130)
        plt.close(fig)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
