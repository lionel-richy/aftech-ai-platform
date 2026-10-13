import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

// Vérifie STATIQUEMENT (code source) que la clé backend n'est jamais exposée
// au navigateur : jamais préfixée NEXT_PUBLIC_, jamais importée hors des
// routes serveur. Un contrôle complémentaire, plus fort, consiste à grepper
// le bundle de production après "next build" (voir docs/FRONTEND_GUIDE.md) :
// ce test-ci s'exécute à chaque run, sans attendre un build complet.
const RACINE = path.resolve(__dirname, "..");
const DOSSIERS_A_IGNORER = new Set(["node_modules", ".next", "tests", "test-results"]);

function listerFichiersSource(dossier: string): string[] {
  const resultats: string[] = [];
  for (const entree of readdirSync(dossier)) {
    if (DOSSIERS_A_IGNORER.has(entree)) continue;
    const cheminComplet = path.join(dossier, entree);
    const infos = statSync(cheminComplet);
    if (infos.isDirectory()) {
      resultats.push(...listerFichiersSource(cheminComplet));
    } else if (/\.(ts|tsx|js|jsx)$/.test(entree)) {
      resultats.push(cheminComplet);
    }
  }
  return resultats;
}

describe("Aucun secret backend exposé côté client", () => {
  const fichiers = listerFichiersSource(RACINE);

  it("aucun fichier source ne référence NEXT_PUBLIC_BACKEND_API_KEY", () => {
    const fichiersSuspects = fichiers.filter((f) => readFileSync(f, "utf-8").includes("NEXT_PUBLIC_BACKEND_API_KEY"));
    expect(fichiersSuspects).toEqual([]);
  });

  it("seul lib/backend.ts lit process.env.BACKEND_API_KEY (jamais un composant client)", () => {
    const fichiersUtilisantLaCle = fichiers.filter(
      (f) =>
        readFileSync(f, "utf-8").includes("process.env.BACKEND_API_KEY") &&
        !f.endsWith("backend-client.test.ts"),
    );
    const chemins = fichiersUtilisantLaCle.map((f) => path.relative(RACINE, f));
    expect(chemins).toEqual(["lib/backend.ts"]);
  });

  it("aucun composant \"use client\" ne référence BACKEND_API_KEY", () => {
    const fichiersSuspects = fichiers.filter((f) => {
      const contenu = readFileSync(f, "utf-8");
      return contenu.startsWith('"use client"') && contenu.includes("BACKEND_API_KEY");
    });
    expect(fichiersSuspects).toEqual([]);
  });

  it("lib/backend.ts importe bien 'server-only' (garde-fou au build)", () => {
    const contenu = readFileSync(path.join(RACINE, "lib", "backend.ts"), "utf-8");
    expect(contenu).toContain('import "server-only"');
  });
});
