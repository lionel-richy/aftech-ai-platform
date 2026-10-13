"use client";

import { useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { Loader2, Plus, Send } from "lucide-react";

import { BackendUnavailableState, ErrorState } from "@/components/ui/StateViews";
import { expliquerErreurHttp } from "@/lib/errorMessages";
import type { AskResponse } from "@/lib/types";
import { useChatHistory } from "@/lib/useChatHistory";
import { AnswerCard } from "./AnswerCard";

const MESSAGE_DEMARRAGE_A_FROID =
  "Le moteur IA démarre. Le premier appel peut prendre quelques minutes.";

const QUESTIONS_EXEMPLES = [
  "Quel est l'objectif principal de l'Epic AI Platform & Model Infrastructure ?",
  "Quel runtime LLM principal est recommandé ?",
  "Quel document contient des informations relatives à Azure ?",
];

export function ChatView() {
  const { tours, ajouter, mettreAJour, nouvelleConversation, hydrate } = useChatHistory();
  const [saisie, setSaisie] = useState("");
  const [envoiEnCours, setEnvoiEnCours] = useState(false);
  const refTextarea = useRef<HTMLTextAreaElement>(null);

  async function envoyer(question: string) {
    const texte = question.trim();
    if (!texte || envoiEnCours) return;

    const id = crypto.randomUUID();
    ajouter({ id, question: texte, enCours: true });
    setSaisie("");
    setEnvoiEnCours(true);

    try {
      const reponseHttp = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: texte, top_k: 8 }),
      });

      if (!reponseHttp.ok) {
        const corps = await reponseHttp.json().catch(() => null);
        const explication = expliquerErreurHttp(reponseHttp.status, corps?.message);
        mettreAJour(id, { enCours: false, erreur: explication });
        return;
      }

      const reponse: AskResponse = await reponseHttp.json();
      mettreAJour(id, { enCours: false, reponse });
    } catch {
      mettreAJour(id, {
        enCours: false,
        erreur: {
          titre: "Backend indisponible",
          description: "Impossible de contacter le serveur.",
          type: "indisponible",
        },
      });
    } finally {
      setEnvoiEnCours(false);
    }
  }

  function gererTouche(evenement: KeyboardEvent<HTMLTextAreaElement>) {
    if (evenement.key === "Enter" && !evenement.shiftKey) {
      evenement.preventDefault();
      envoyer(saisie);
    }
    // Shift+Enter : comportement par défaut du textarea (nouvelle ligne).
  }

  const backendIndisponible = tours.some((t) => t.erreur?.type === "indisponible");

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-end border-b border-[var(--border)] px-4 py-2 md:px-6">
        <button
          type="button"
          onClick={nouvelleConversation}
          className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--surface-elevated)] hover:text-[var(--text-primary)]"
        >
          <Plus aria-hidden className="h-3.5 w-3.5" />
          Nouvelle conversation
        </button>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-6 md:px-6">
        {hydrate && tours.length === 0 && (
          <div className="mx-auto max-w-lg space-y-3 pt-8 text-center">
            <p className="text-sm text-[var(--text-secondary)]">
              Posez une question sur les documents indexés. Exemples :
            </p>
            <div className="flex flex-col gap-2">
              {QUESTIONS_EXEMPLES.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => envoyer(q)}
                  className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-left text-sm text-[var(--text-secondary)] hover:border-primary/40 hover:text-[var(--text-primary)]"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {tours.map((tour) => (
          <div key={tour.id} className="space-y-2">
            <div className="ml-auto max-w-[80%] rounded-[var(--radius-lg)] bg-primary/10 px-4 py-2.5 text-sm text-[var(--text-primary)]">
              {tour.question}
            </div>

            {tour.enCours && (
              <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
                <Loader2 aria-hidden className="h-4 w-4 animate-spin motion-reduce:animate-none" />
                {MESSAGE_DEMARRAGE_A_FROID}
              </div>
            )}

            {tour.erreur && !tour.enCours && tour.erreur.type === "indisponible" && (
              <BackendUnavailableState description={tour.erreur.description} />
            )}
            {tour.erreur && !tour.enCours && tour.erreur.type === "erreur" && (
              <ErrorState title={tour.erreur.titre} description={tour.erreur.description} />
            )}

            {tour.reponse && !tour.enCours && <AnswerCard reponse={tour.reponse} />}
          </div>
        ))}
      </div>

      <div className="border-t border-[var(--border)] p-4 md:p-6">
        {backendIndisponible && (
          <p className="mb-2 text-xs text-warning">
            Le backend semble indisponible — vérifiez qu&apos;il tourne (voir Administration).
          </p>
        )}
        <div className="flex items-end gap-2 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-2">
          <label htmlFor="assistant-saisie" className="sr-only">
            Votre question
          </label>
          <textarea
            id="assistant-saisie"
            ref={refTextarea}
            value={saisie}
            onChange={(e) => setSaisie(e.target.value)}
            onKeyDown={gererTouche}
            placeholder="Posez votre question… (Entrée pour envoyer, Maj+Entrée pour une nouvelle ligne)"
            rows={1}
            className="max-h-40 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none"
          />
          <button
            type="button"
            onClick={() => envoyer(saisie)}
            disabled={envoiEnCours || !saisie.trim()}
            aria-label="Envoyer la question"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-primary text-[var(--bg)] transition-opacity disabled:opacity-40"
          >
            <Send aria-hidden className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
