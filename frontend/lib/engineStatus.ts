"use client";

import { useEffect, useState } from "react";

// État PARTAGÉ (dans l'onglet du navigateur) du moteur IA (Qwen + BGE-M3 sur
// GPU Modal) — mis à jour UNIQUEMENT par de vraies interactions (une
// question envoyée à /api/ask, ou une vérification manuelle du GPU depuis le
// tableau de bord). JAMAIS par une surveillance automatique : c'est tout le
// but de séparer cet état du ping périodique de BackendStatusIndicator (voir
// lib/availability.ts), qui ne doit JAMAIS appeler une route GPU.
//
// Singleton module (pas de contexte React) : simple, pas de nouvelle
// dépendance, et volontairement remis à "veille" à chaque rechargement de
// page (aucune information "GPU prêt" ne doit survivre à un rechargement :
// on ne SAIT plus si le conteneur est encore chaud).

export type EtatMoteur = "veille" | "demarrage" | "pret" | "indisponible";

export interface EtatMoteurSnapshot {
  etat: EtatMoteur;
  // null si inconnu ou si le moteur est en veille — jamais une valeur
  // inventée (exigence : ne jamais afficher une fausse mémoire GPU).
  vramUtiliseeOctets: number | null;
  vramTotaleOctets: number | null;
}

const ETAT_INITIAL: EtatMoteurSnapshot = {
  etat: "veille",
  vramUtiliseeOctets: null,
  vramTotaleOctets: null,
};

let etatActuel: EtatMoteurSnapshot = ETAT_INITIAL;
const abonnes = new Set<(etat: EtatMoteurSnapshot) => void>();

export function definirEtatMoteur(etat: EtatMoteurSnapshot): void {
  etatActuel = etat;
  for (const f of abonnes) f(etatActuel);
}

export function etatMoteurActuel(): EtatMoteurSnapshot {
  return etatActuel;
}

export function sabonnerEtatMoteur(f: (etat: EtatMoteurSnapshot) => void): () => void {
  abonnes.add(f);
  return () => abonnes.delete(f);
}

// Pour les tests uniquement : remet le singleton à son état initial, sinon
// l'ordre d'exécution des fichiers de test se contaminerait entre eux.
export function reinitialiserEtatMoteurPourLesTests(): void {
  etatActuel = ETAT_INITIAL;
}

export function useEtatMoteur(): EtatMoteurSnapshot {
  const [etat, setEtat] = useState(etatMoteurActuel);
  useEffect(() => sabonnerEtatMoteur(setEtat), []);
  return etat;
}
