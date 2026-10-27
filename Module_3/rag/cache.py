"""Cache LRU des réponses : une question répétée ne rappelle ni l'index ni le LLM.

La clé contient la version de l'index de l'étudiant : dès qu'un cours est ajouté
ou retiré, la version change et les anciennes réponses ne sont plus servies.
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from typing import Any

from app.core.text import normalize


def cache_key(student_id: int, index_version: int, question: str, course_id: int | None, k: int,
              backend: str, prompt_version: str) -> str:
    """Empreinte SHA-256 de tout ce qui peut changer la réponse."""
    raw = "|".join([str(student_id), str(index_version), normalize(question), str(course_id), str(k),
                    backend, prompt_version])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class LRUCache:
    """Cache borné, sûr entre threads, avec compteurs de succès et d'échecs."""

    def __init__(self, max_size: int) -> None:
        self.max_size = max_size
        self._data: OrderedDict[str, Any] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Any | None:
        """Retourne la valeur et la marque comme récente, ou None."""
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
                self.hits += 1
                return self._data[key]
            self.misses += 1
            return None

    def set(self, key: str, value: Any) -> None:
        """Ajoute une valeur, en évinçant la plus ancienne si le cache est plein."""
        if self.max_size == 0:
            return
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self.max_size:
                self._data.popitem(last=False)

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)
