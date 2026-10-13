"""Authentification par clé API et configuration CORS.

La clé attendue vient TOUJOURS d'une variable d'environnement (BACKEND_API_KEY),
jamais d'une valeur codée en dur dans le code — c'est ce qui permet de la
changer sans toucher au code, et de ne jamais la committer dans Git.
"""

import os

from fastapi import Header, HTTPException, status


def get_cors_origins() -> list[str]:
    """Liste des origines autorisées (CORS), configurée via BACKEND_CORS_ORIGINS
    (une ou plusieurs URLs séparées par des virgules). Par défaut : seulement
    le frontend Next.js en développement local."""
    raw = os.environ.get("BACKEND_CORS_ORIGINS", "http://localhost:3000")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def verify_api_key(authorization: str | None = Header(default=None)) -> None:
    """Dépendance FastAPI : vérifie l'en-tête `Authorization: Bearer <clé>`.

    Utilisée sur toutes les routes sauf /health (qui doit rester consultable
    par un simple contrôle de supervision, sans secret).
    """
    expected = os.environ.get("BACKEND_API_KEY")
    if not expected:
        # Pas de clé configurée côté serveur : on refuse plutôt que d'accepter
        # n'importe quelle requête sans contrôle.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="BACKEND_API_KEY n'est pas configurée côté serveur.",
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Clé API manquante.")

    presented = authorization.removeprefix("Bearer ").strip()
    if presented != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Clé API invalide.")
