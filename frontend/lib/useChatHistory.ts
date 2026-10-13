"use client";

import { useCallback, useEffect, useState } from "react";

import type { ErreurExplicationCles } from "./errorMessages";
import type { AskResponse } from "./types";

export interface ChatTurn {
  id: string;
  question: string;
  reponse?: AskResponse;
  // Clés de traduction (namespace "Errors"), pas de texte résolu : permet à
  // l'historique de rester correct même après un changement de langue.
  erreur?: ErreurExplicationCles;
  enCours?: boolean;
}

const CLE_LOCALSTORAGE = "aftech.assistant.historique";

function litHistoriqueLocal(): ChatTurn[] {
  try {
    const brut = window.localStorage.getItem(CLE_LOCALSTORAGE);
    if (!brut) return [];
    const valeur = JSON.parse(brut);
    return Array.isArray(valeur) ? valeur : [];
  } catch {
    return [];
  }
}

// Historique LOCAL à la session du navigateur uniquement (exigence : "ne pas
// inventer une mémoire conversationnelle côté backend si elle n'existe pas
// encore" — le backend ne connaît rien de cet historique).
export function useChatHistory() {
  const [tours, setTours] = useState<ChatTurn[]>([]);
  const [hydrate, setHydrate] = useState(false);

  useEffect(() => {
    // Lecture unique d'un système externe (localStorage, inaccessible au
    // rendu serveur) après montage : cas justifiant explicitement cette règle.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTours(litHistoriqueLocal());
    setHydrate(true);
  }, []);

  useEffect(() => {
    if (!hydrate) return;
    try {
      window.localStorage.setItem(CLE_LOCALSTORAGE, JSON.stringify(tours));
    } catch {
      // Stockage indisponible : l'historique reste fonctionnel pour la session en cours.
    }
  }, [tours, hydrate]);

  const ajouter = useCallback((tour: ChatTurn) => {
    setTours((precedents) => [...precedents, tour]);
  }, []);

  const mettreAJour = useCallback((id: string, patch: Partial<ChatTurn>) => {
    setTours((precedents) => precedents.map((t) => (t.id === id ? { ...t, ...patch } : t)));
  }, []);

  const nouvelleConversation = useCallback(() => {
    setTours([]);
    try {
      window.localStorage.removeItem(CLE_LOCALSTORAGE);
    } catch {
      // Rien de grave si on ne peut pas nettoyer le stockage.
    }
  }, []);

  return { tours, ajouter, mettreAJour, nouvelleConversation, hydrate };
}
