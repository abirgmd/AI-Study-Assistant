"""Entraîne et compare les modèles de classification des cours (module 5).

Méthode (pour ne pas « tricher » avec le jeu de test) :
  1. Pour chaque candidat : GridSearchCV en StratifiedKFold(5) sur train.csv, score F1 macro.
  2. Le modèle final est CHOISI uniquement sur la validation croisée : F1 macro, puis, pour les
     modèles à moins d'un point, la log-loss (qualité des probabilités, utilisées pour le seuil).
  3. Le test réel (test_reel.csv, vrais supports de cours) ne sert qu'à RAPPORTER les performances
     de tous les candidats, jamais à choisir.
  4. Le modèle final est réentraîné sur tout train.csv puis sauvegardé (joblib + métadonnées).

Résultats : reports/classification/ (comparatif.csv, resume.json, matrice de confusion, termes).

Exemple :
  python scripts/train_classifier.py --embedding hashing
  python scripts/train_classifier.py --embedding sentence-transformers
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import platform
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.metrics import accuracy_score, f1_score, log_loss
from sklearn.model_selection import GridSearchCV, StratifiedKFold, cross_val_predict

SERVICE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_DIR))

from app.config import load_categories  # noqa: E402
from app.modules.classification.classifier import top_terms_per_class  # noqa: E402
from app.modules.classification.models import build_candidates  # noqa: E402

DATA = SERVICE_DIR / "data" / "classification"
REPORTS = SERVICE_DIR / "reports" / "classification"
MODELS = SERVICE_DIR / "models"
TIE_MARGIN = 0.01
TARGET_PRECISION = 0.90


def choose_threshold(confidences: np.ndarray, correct: np.ndarray) -> tuple[float, list[dict]]:
    """Plus petit seuil tel que l'exactitude des prédictions acceptées atteigne TARGET_PRECISION.

    Un seuil plus bas classerait plus de cours automatiquement, mais avec plus d'erreurs affichées.
    """
    rows, chosen = [], None
    for threshold in np.round(np.arange(0.0, 0.95, 0.05), 2):
        accepted = confidences >= threshold
        accuracy = float(correct[accepted].mean()) if accepted.any() else float("nan")
        rows.append({"seuil": float(threshold), "part_classee": round(float(accepted.mean()), 4),
                     "exactitude_parmi_classes": round(accuracy, 4)})
        if chosen is None and accepted.any() and accuracy >= TARGET_PRECISION:
            chosen = float(threshold)
    return (chosen if chosen is not None else 0.5), rows


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def model_size_mb(estimator) -> float:
    buffer = io.BytesIO()
    joblib.dump(estimator, buffer, compress=3)
    return buffer.getbuffer().nbytes / 1024**2


def latency_ms(estimator, texts: list[str], repeats: int = 3) -> float:
    """Temps moyen de prédiction d'UN document (appel par appel, comme en production)."""
    sample = texts[:30]
    timings = []
    for _ in range(repeats):
        start = time.perf_counter()
        for text in sample:
            estimator.predict_proba([text])
        timings.append((time.perf_counter() - start) * 1000 / len(sample))
    return float(np.median(timings))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--embedding", default="sentence-transformers", choices=["hashing", "sentence-transformers"])
    parser.add_argument("--only", nargs="*", help="limiter à certains candidats (nb logreg svm rf emb_logreg)")
    args = parser.parse_args()

    categories = load_categories()
    train = read_csv(DATA / "train.csv")
    test = read_csv(DATA / "test_reel.csv")
    x_train, y_train = [r["text"] for r in train], [r["label"] for r in train]
    x_test, y_test = [r["text"] for r in test], [r["label"] for r in test]
    present = sorted(set(y_test), key=categories.index)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    REPORTS.mkdir(parents=True, exist_ok=True)
    MODELS.mkdir(parents=True, exist_ok=True)

    results, fitted = [], {}
    for candidate in build_candidates(embedding_backend=args.embedding):
        if args.only and candidate.key not in args.only:
            continue
        print(f"→ {candidate.label}", flush=True)
        search = GridSearchCV(candidate.pipeline, candidate.grid, cv=cv, scoring="f1_macro", n_jobs=1, refit=True)
        start = time.perf_counter()
        search.fit(x_train, y_train)
        search_s = time.perf_counter() - start
        best = search.best_estimator_
        index = search.best_index_
        predictions = best.predict(x_test)
        results.append({
            "cle": candidate.key,
            "modele": candidate.label,
            "meilleurs_parametres": json.dumps(search.best_params_, ensure_ascii=False, default=str),
            "cv_f1_macro": round(float(search.best_score_), 4),
            "cv_f1_ecart_type": round(float(search.cv_results_["std_test_score"][index]), 4),
            "entrainement_final_s": round(float(search.refit_time_), 3),
            "recherche_grille_s": round(search_s, 1),
            "test_reel_exactitude": round(accuracy_score(y_test, predictions), 4),
            "test_reel_f1_macro": round(f1_score(y_test, predictions, labels=present, average="macro",
                                                 zero_division=0), 4),
            "latence_ms_par_document": round(latency_ms(best, x_test), 2),
            "taille_mo": round(model_size_mb(best), 2),
        })
        # Qualité des probabilités (log-loss en validation croisée) : l'application affiche une
        # confiance et applique un seuil, il faut donc des probabilités fiables, pas seulement un bon F1.
        cv_proba = cross_val_predict(best, x_train, y_train, cv=cv, method="predict_proba")
        results[-1]["cv_log_loss"] = round(float(log_loss(y_train, cv_proba, labels=list(best.classes_))), 4)
        fitted[candidate.key] = best
        print(f"   CV F1 macro {results[-1]['cv_f1_macro']} | test réel F1 macro {results[-1]['test_reel_f1_macro']}")

    # Choix sur la validation croisée uniquement : F1 macro (à TIE_MARGIN près), puis log-loss.
    # La latence n'est PAS un critère : les écarts mesurés (quelques ms par document, une seule
    # prédiction par import) sont du bruit de mesure et rendaient le choix instable (BUG_REPORT B9).
    best_cv = max(r["cv_f1_macro"] for r in results)
    finalists = [r for r in results if r["cv_f1_macro"] >= best_cv - TIE_MARGIN]
    chosen = min(finalists, key=lambda r: (r["cv_log_loss"], -r["cv_f1_macro"]))
    for r in results:
        r["retenu"] = "oui" if r is chosen else ""
    with (REPORTS / "comparatif.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)

    final = fitted[chosen["cle"]]
    # Probabilités hors échantillon (validation croisée) du modèle retenu : elles servent à
    # (1) repérer les textes ambigus à relire, (2) choisir le seuil de confiance SANS le test réel.
    cv_proba = cross_val_predict(final, x_train, y_train, cv=cv, method="predict_proba")
    classes = list(final.classes_)
    cv_predictions = [classes[i] for i in cv_proba.argmax(axis=1)]
    threshold, threshold_rows = choose_threshold(cv_proba.max(axis=1),
                                                 np.array(cv_predictions) == np.array(y_train))
    with (REPORTS / "seuil_validation_croisee.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(threshold_rows[0]))
        writer.writeheader()
        writer.writerows(threshold_rows)
    flagged = 0
    for row, predicted in zip(train, cv_predictions, strict=True):
        row["a_relire"] = "" if predicted == row["label"] else f"prédit : {predicted}"
        flagged += predicted != row["label"]
    with (DATA / "train.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["text", "label", "source", "a_relire"])
        writer.writeheader()
        writer.writerows(train)

    version = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    meta = {
        "version": version,
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "modele": chosen["modele"],
        "cle": chosen["cle"],
        "parametres": json.loads(chosen["meilleurs_parametres"]),
        "embedding_backend": args.embedding,
        "categories": categories,
        "metriques": {k: chosen[k] for k in ("cv_f1_macro", "cv_f1_ecart_type", "cv_log_loss", "test_reel_exactitude",
                                               "test_reel_f1_macro", "latence_ms_par_document", "taille_mo")},
        "donnees": {"entrainement": len(train), "test_reel": len(test), "classes_du_test_reel": present},
        "textes_a_relire": int(flagged),
        "seuil_confiance": threshold,
        "regle_du_seuil": f"plus petit seuil donnant au moins {TARGET_PRECISION:.0%} d'exactitude parmi les cours "
                          "classés automatiquement, mesuré en validation croisée sur l'entraînement",
        "versions": {"python": platform.python_version(), "scikit-learn": sklearn.__version__,
                     "numpy": np.__version__, "joblib": joblib.__version__},
        "regle_de_choix": f"meilleur F1 macro en validation croisée (à {TIE_MARGIN} près), puis plus faible "
                          "log-loss en validation croisée ; le test réel n'intervient pas dans le choix",
    }
    joblib.dump({"pipeline": final, "categories": categories, "meta": meta}, MODELS / "classifier.joblib", compress=3)
    (MODELS / "classifier_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (REPORTS / "termes_par_categorie.json").write_text(
        json.dumps(top_terms_per_class(final, 10), ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"retenu": chosen["modele"], **meta["metriques"], "textes_a_relire": flagged,
                      "seuil_confiance": threshold},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
