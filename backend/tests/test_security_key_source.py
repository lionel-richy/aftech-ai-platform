"""Vérifie STATIQUEMENT que BACKEND_API_KEY vient exclusivement de
l'environnement (donc, sur Modal, exclusivement du secret
"aftech-backend-secrets") — jamais une valeur codée en dur dans le code."""

import re
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _fichiers_python(dossier: Path):
    return [p for p in dossier.rglob("*.py") if "tests" not in p.parts and "__pycache__" not in p.parts]


def test_security_py_ne_lit_la_cle_que_depuis_os_environ():
    contenu = (BACKEND_DIR / "app" / "security.py").read_text(encoding="utf-8")
    assert 'os.environ.get("BACKEND_API_KEY")' in contenu
    # Aucune valeur par défaut codée en dur pour cette variable précise
    # (ex. os.environ.get("BACKEND_API_KEY", "quelque-chose")).
    assert not re.search(r'os\.environ\.get\("BACKEND_API_KEY",\s*["\']', contenu)


def test_aucun_fichier_backend_ne_contient_de_cle_codee_en_dur():
    motif_suspect = re.compile(r'BACKEND_API_KEY\s*=\s*["\'][^"\']+["\']')
    fichiers_suspects = []
    for fichier in _fichiers_python(BACKEND_DIR):
        contenu = fichier.read_text(encoding="utf-8")
        if motif_suspect.search(contenu):
            fichiers_suspects.append(str(fichier.relative_to(BACKEND_DIR)))
    assert fichiers_suspects == []


def test_modal_app_ne_definit_pas_backend_api_key_lui_meme():
    """Seul le secret Modal "aftech-backend-secrets" doit injecter cette clé —
    modal_app.py ne doit jamais la fixer lui-même (ex. os.environ.setdefault).

    "BACKEND_API_KEY" peut légitimement apparaître en commentaire/docstring
    (ex. la commande "modal secret create ... BACKEND_API_KEY=<valeur>") :
    on vérifie l'absence d'une AFFECTATION réelle, pas l'absence totale du nom.
    """
    contenu = (BACKEND_DIR / "app" / "modal_app.py").read_text(encoding="utf-8")
    motifs_interdits = [
        r'os\.environ\["BACKEND_API_KEY"\]\s*=',
        r"os\.environ\.setdefault\(\s*[\"']BACKEND_API_KEY[\"']",
        r'BACKEND_API_KEY\s*=\s*["\']',
    ]
    for motif in motifs_interdits:
        assert not re.search(motif, contenu), f"Affectation suspecte trouvée ({motif})"
    assert "aftech-backend-secrets" in contenu
