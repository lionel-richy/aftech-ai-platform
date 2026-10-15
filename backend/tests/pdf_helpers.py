"""Génère de VRAIS PDF minimaux en mémoire, pour tester la validation et
l'extraction sans dépendre de fichiers binaires committés.

pdf_valide() construit le PDF à la main (plutôt que via pypdf.PdfWriter) car
PdfWriter().add_blank_page() produit des pages sans AUCUN contenu texte —
or index_builder.py a besoin d'un vrai texte extractible pour produire des
chunks (une page blanche donne 0 passage, ce qui fait échouer la
reconstruction avec IndexInvalide("Aucun passage à indexer")). pypdf lit ce
PDF fait main correctement (avec un avertissement de récupération mineur sur
le xref, sans incidence sur l'extraction)."""

import io

from pypdf import PdfWriter


def pdf_valide(nb_pages: int = 1, texte: str = "Texte de test pour extraction.") -> bytes:
    pages = []
    for _ in range(nb_pages):
        flux = f"BT /F1 12 Tf 10 150 Td ({texte}) Tj ET".encode("latin-1")
        pages.append(flux)

    objets = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[" + b" ".join(f"{3 + i} 0 R".encode() for i in range(nb_pages)) + b"]/Count "
        + str(nb_pages).encode()
        + b">>",
    ]
    numero_contenu_base = 3 + nb_pages
    for i in range(nb_pages):
        objets.append(
            (
                f"<</Type/Page/Parent 2 0 R/Resources<</Font<</F1 {numero_contenu_base + nb_pages} 0 R>>>>"
                f"/MediaBox[0 0 200 200]/Contents {numero_contenu_base + i} 0 R>>"
            ).encode()
        )
    for flux in pages:
        objets.append(f"<</Length {len(flux)}>>\nstream\n".encode() + flux + b"\nendstream")
    objets.append(b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>")

    corps = b"%PDF-1.4\n"
    for i, contenu in enumerate(objets, start=1):
        corps += f"{i} 0 obj".encode() + contenu + b"endobj\n"
    nb_objets_total = len(objets) + 1
    corps += (
        b"xref\n0 " + str(nb_objets_total).encode() + b"\n"
        b"trailer<</Size " + str(nb_objets_total).encode() + b"/Root 1 0 R>>\n"
        b"startxref\n0\n%%EOF\n"
    )
    return corps


def pdf_chiffre() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("motdepasse")
    tampon = io.BytesIO()
    writer.write(tampon)
    return tampon.getvalue()
