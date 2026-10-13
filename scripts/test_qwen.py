import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

# Nom du modèle sur Hugging Face
MODEL_NAME = "Qwen/Qwen3-4B-Instruct-2507"

# Question de test (pas de données réelles, juste un exemple fixe)
QUESTION = "Explique simplement le rôle d'un assistant documentaire dans une entreprise."

MAX_NEW_TOKENS = 250


def main():
    # On vérifie qu'un GPU est disponible, sinon le script n'a pas d'intérêt
    if not torch.cuda.is_available():
        raise RuntimeError("Aucun GPU détecté. Ce script doit tourner sur une session Colab avec GPU.")

    # Nom du GPU (ex: "Tesla T4")
    gpu_name = torch.cuda.get_device_name(0)
    print(f"GPU détecté : {gpu_name}")

    # Mémoire totale du GPU, convertie en Go pour être lisible
    total_memory_go = torch.cuda.get_device_properties(0).total_memory / (1024**3)
    print(f"Mémoire GPU totale : {total_memory_go:.2f} Go")

    # bfloat16 est plus stable mais pas supporté par tous les GPU (ex: T4 ne le supporte pas)
    # On bascule sur float16 si bfloat16 n'est pas disponible
    if torch.cuda.is_bf16_supported():
        compute_dtype = torch.bfloat16
        print("Type de calcul utilisé : bfloat16")
    else:
        compute_dtype = torch.float16
        print("Type de calcul utilisé : float16 (bfloat16 non supporté sur ce GPU)")

    # Configuration de la quantification 4 bits (réduit fortement la mémoire utilisée)
    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=compute_dtype,
        bnb_4bit_use_double_quant=True,
    )

    print(f"Chargement du modèle {MODEL_NAME} en 4 bits...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        quantization_config=quant_config,
        device_map="auto",
    )

    # On réinitialise le compteur de mémoire pour mesurer seulement l'inférence
    torch.cuda.reset_peak_memory_stats()

    # Qwen3 est un modèle de chat : on utilise le format de conversation
    # et on demande explicitement une réponse en français
    messages = [
        {"role": "system", "content": "Tu réponds toujours en français, de façon simple et claire."},
        {"role": "user", "content": QUESTION},
    ]
    # return_dict=True : on récupère un dictionnaire (input_ids + attention_mask)
    # plutôt qu'un simple tensor, pour que generate() reçoive aussi l'attention_mask
    inputs = tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        return_tensors="pt",
        return_dict=True,
    ).to(model.device)

    print("Génération de la réponse...")
    start_time = time.perf_counter()
    output_ids = model.generate(
        **inputs,
        max_new_tokens=MAX_NEW_TOKENS,
        do_sample=False,
    )
    elapsed_seconds = time.perf_counter() - start_time

    # On ne garde que les tokens générés (pas la question renvoyée dans la sortie)
    generated_ids = output_ids[0][inputs["input_ids"].shape[-1]:]
    response = tokenizer.decode(generated_ids, skip_special_tokens=True)

    # Mémoire GPU utilisée pendant la génération (pic atteint)
    peak_memory_go = torch.cuda.max_memory_allocated() / (1024**3)

    print("\n--- Question ---")
    print(QUESTION)
    print("\n--- Réponse ---")
    print(response)
    print("\n--- Mesures ---")
    print(f"Temps de réponse : {elapsed_seconds:.2f} secondes")
    print(f"Mémoire GPU utilisée (pic) : {peak_memory_go:.2f} Go")


if __name__ == "__main__":
    main()
