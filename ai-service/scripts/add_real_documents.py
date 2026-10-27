"""Ajoute de VRAIS supports de cours au jeu de test de la classification (module 5).

Le test réel fourni ne couvre que 6 catégories sur 8 (les supports disponibles venaient du
module IA for Software Engineering). Pour mesurer correctement le modèle, déposez des cours
d'autres matières dans :

    data/classification/real_courses/<Catégorie exacte>/<fichier>.pdf|.docx|.txt

par exemple « data/classification/real_courses/Mathématiques/algebre_chap2.pdf », puis lancez :

    python scripts/add_real_documents.py
    python scripts/train_classifier.py
    python scripts/evaluate_classifier.py

Chaque document est découpé en extraits d'environ 600 caractères (au plus 15 par document) et
ajouté à test_reel.csv avec la source « reel_cours:<fichier> ». Les extraits déjà présents ne sont
pas ajoutés deux fois.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_DIR))

from app.config import load_categories  # noqa: E402
from app.core.chunking import chunk_pages  # noqa: E402
from app.core.extraction import SUPPORTED_EXTENSIONS, extract_pages  # noqa: E402
from app.errors import ExtractionError  # noqa: E402

DATA = SERVICE_DIR / "data" / "classification"
MAX_PER_DOCUMENT = 15


def main() -> None:
    root = DATA / "real_courses"
    if not root.is_dir():
        root.mkdir(parents=True)
        print(f"Dossier créé : {root}. Ajoutez-y un sous-dossier par catégorie, puis relancez.")
        return
    categories = load_categories()
    path = DATA / "test_reel.csv"
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    known = {r["text"] for r in rows}
    added = 0
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        if folder.name not in categories:
            print(f"Ignoré : « {folder.name} » n'est pas une catégorie ({', '.join(categories)}).")
            continue
        for document in sorted(folder.iterdir()):
            if document.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            try:
                chunks = chunk_pages(extract_pages(document), size=600, overlap=0)
            except ExtractionError as exc:
                print(f"Ignoré : {document.name} ({exc.message})")
                continue
            for chunk in [c for c in chunks if len(c.text.split()) >= 30][:MAX_PER_DOCUMENT]:
                if chunk.text not in known:
                    rows.append({"text": chunk.text, "label": folder.name,
                                 "source": f"reel_cours:{document.name}#bloc{chunk.rank}"})
                    known.add(chunk.text)
                    added += 1
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["text", "label", "source"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"{added} extraits ajoutés ; test réel : {len(rows)} extraits.")


if __name__ == "__main__":
    main()
