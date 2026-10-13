"""Compteurs en mémoire depuis le démarrage du process.

Volontairement simple (pas de base de données) : ces métriques servent le
tableau de bord de la Demo V1, et ne doivent JAMAIS être inventées côté
frontend — si une métrique n'a pas encore été mesurée, elle doit rester
absente/None plutôt que d'afficher un chiffre fictif.
"""

import threading
import time

STATUTS_CONNUS = ("COMPLETE", "PARTIAL", "NOT_FOUND")


class MetricsStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._start_time = time.monotonic()
        self.requests_total = 0
        self.status_counts = {statut: 0 for statut in STATUTS_CONNUS}
        self.errors_total = 0
        self._latences_secondes: list[float] = []

    def record_request(self, statut: str, latence_secondes: float) -> None:
        with self._lock:
            self.requests_total += 1
            if statut in self.status_counts:
                self.status_counts[statut] += 1
            self._latences_secondes.append(latence_secondes)

    def record_error(self) -> None:
        with self._lock:
            self.errors_total += 1

    def reset(self) -> None:
        """Réservé aux tests : remet les compteurs à zéro pour isoler chaque test
        du singleton partagé par le process."""
        with self._lock:
            self._start_time = time.monotonic()
            self.requests_total = 0
            self.status_counts = {statut: 0 for statut in STATUTS_CONNUS}
            self.errors_total = 0
            self._latences_secondes = []

    def snapshot(self) -> dict:
        with self._lock:
            latence_moyenne = (
                sum(self._latences_secondes) / len(self._latences_secondes)
                if self._latences_secondes
                else None
            )
            return {
                "uptime_secondes": time.monotonic() - self._start_time,
                "requests_total": self.requests_total,
                "status_complete": self.status_counts["COMPLETE"],
                "status_partial": self.status_counts["PARTIAL"],
                "status_not_found": self.status_counts["NOT_FOUND"],
                "errors_total": self.errors_total,
                "latence_moyenne_secondes": latence_moyenne,
            }


# Un seul magasin de métriques par process — cohérent avec "une métrique par
# conteneur", pas de partage entre conteneurs différents.
metrics_store = MetricsStore()
