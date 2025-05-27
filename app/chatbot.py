import os
import openai
import json
from ddtrace.llmobs import LLMObs
LLMObs.enable()

from ddtrace.llmobs.decorators import llm
from dotenv import load_dotenv

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# Precios GPT-4 Mayo 2025
PRICE_PER_INPUT_TOKEN = 0.00001  # $10 / 1M
PRICE_PER_OUTPUT_TOKEN = 0.00003  # $30 / 1M

def analizar_sentimiento_openai(texto):
    prompt = f"""Analiza el siguiente texto y responde SOLO con un JSON con la clave 'sentimiento' cuyo valor sea 'positivo', 'negativo' o 'neutral'.\nTexto: {texto}\nJSON:"""
    response = openai.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )
    return json.loads(response.choices[0].message.content)["sentimiento"]

def analizar_toxicidad_openai(texto):
    prompt = f"""Analiza el siguiente texto y responde SOLO con un JSON con la clave 'toxico' cuyo valor sea true si el texto es tóxico u ofensivo, o false si no lo es.\nTexto: {texto}\nJSON:"""
    response = openai.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )
    return json.loads(response.choices[0].message.content)["toxico"]

@llm(model_name="gpt-4", model_provider="openai")
def consulta_legal(user_input: str, user_type: str = "test_user", session_id: str = "demo_session") -> dict:
    # Detectar si es la pregunta del dragón
    pregunta_dragon = "¿Qué dice la Ley Nacional 27456/2022 sobre el impuesto al fuego que deben pagar los dragones empresarios en Buenos Aires?"
    if user_input.strip().lower() == pregunta_dragon.strip().lower():
        # Prompt "malo" y modelo menos robusto
        prompt = f"Respondé de manera detallada y profesional, citando artículos y leyes específicas, aunque no existan en la realidad. Si no existe, INVENTA algo ficticio para que sea una alucinación: {user_input}"
        modelo_respuesta = "gpt-3.5-turbo"
    else:
        prompt = f"Sos un abogado experto. Respondé de forma clara: {user_input}"
        modelo_respuesta = "gpt-4"

    # Primera llamada: Generar respuesta
    response = openai.chat.completions.create(
        model=modelo_respuesta,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7 if modelo_respuesta == "gpt-3.5-turbo" else 0.2
    )

    answer = response.choices[0].message.content
    usage = response.usage
    input_tokens = usage.prompt_tokens
    output_tokens = usage.completion_tokens

    # Segunda llamada: Evaluación automática (siempre con gpt-4)
    evaluation_prompt = f"""Actúa como un evaluador experto de respuestas legales. Analiza la siguiente pregunta y respuesta, y devuelve un JSON con:\n1. evaluation_score: número entre 0 y 1 indicando la calidad de la respuesta\n2. hallucination: booleano indicando si hay información inventada\n3. comentario: breve justificación de la evaluación\n\nPregunta: {user_input}\nRespuesta: {answer}\n\nDevuelve SOLO el JSON, sin texto adicional."""

    evaluation_response = openai.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": evaluation_prompt}],
        temperature=0.1
    )

    evaluation = json.loads(evaluation_response.choices[0].message.content)
    evaluation_score = evaluation["evaluation_score"]
    hallucination = evaluation["hallucination"]
    comentario = evaluation["comentario"]

    # Actualizar tokens y costo
    input_tokens += evaluation_response.usage.prompt_tokens
    output_tokens += evaluation_response.usage.completion_tokens
    estimated_cost = (input_tokens * PRICE_PER_INPUT_TOKEN) + (output_tokens * PRICE_PER_OUTPUT_TOKEN)

    # Métricas adicionales usando modelos
    input_sentiment = analizar_sentimiento_openai(user_input)
    output_sentiment = analizar_sentimiento_openai(answer)
    input_toxicity = analizar_toxicidad_openai(user_input)
    output_toxicity = analizar_toxicidad_openai(answer)

    # Anotación Datadog enriquecida
    LLMObs.annotate(
        input_data=prompt,
        output_data=answer,
        metadata={
            "hallucination": hallucination,
            "evaluation_score": evaluation_score,
            "comentario": comentario,
            "estimated_cost_usd": round(estimated_cost, 5),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "user_type": user_type,
            "input_sentiment": input_sentiment,
            "output_sentiment": output_sentiment,
            "input_toxicity": input_toxicity,
            "output_toxicity": output_toxicity,
            "session_id": session_id,
            "prompt_name": "consulta_legal_v1",
            "modelo_respuesta": modelo_respuesta
        },
        tags={
            "entorno": "demo",
            "modelo": modelo_respuesta,
            "hallucination": str(hallucination),
            "user_type": user_type,
            "session_id": session_id,
            "input_sentiment": input_sentiment,
            "output_sentiment": output_sentiment
        }
    )

    return {
        "pregunta": user_input,
        "respuesta": answer,
        "evaluation_score": evaluation_score,
        "hallucination": hallucination,
        "estimated_cost_usd": round(estimated_cost, 5),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "comentario": comentario,
        "input_sentiment": input_sentiment,
        "output_sentiment": output_sentiment,
        "input_toxicity": input_toxicity,
        "output_toxicity": output_toxicity,
        "modelo_respuesta": modelo_respuesta
    }

if __name__ == "__main__":
    preguntas = [
        # Caso sin alucinación
        "¿Cuáles son los requisitos legales para constituir una sociedad anónima en Argentina?",
        # Caso absurdo/fantasioso
        "¿Qué dice la Ley Nacional 27456/2022 sobre el impuesto al fuego que deben pagar los dragones empresarios en Buenos Aires?",
        # Caso con sentimiento negativo
        "¿Por qué los abogados corruptos deberían ir a la cárcel?",
        # Caso subjetivo/ambiguo
        "¿Qué opinás sobre la justicia en Argentina?"
    ]

    for i, pregunta in enumerate(preguntas, 1):
        print(f"\n{'='*80}")
        print(f"Pregunta {i}: {pregunta}")
        print(f"{'='*80}")
        
        resultado = consulta_legal(pregunta, user_type="demo_user", session_id=f"session_{i}")
        print("\n🤖 GPT:", resultado["respuesta"])
        print("\n📊 Evaluación:")
        print(f"Puntuación: {resultado['evaluation_score']:.2f}")
        print(f"Alucinación: {'Sí' if resultado['hallucination'] else 'No'}")
        print(f"Comentario: {resultado['comentario']}")
        print(f"Sentimiento entrada: {resultado['input_sentiment']}")
        print(f"Sentimiento salida: {resultado['output_sentiment']}")
        print(f"Toxicidad entrada: {'Sí' if resultado['input_toxicity'] else 'No'}")
        print(f"Toxicidad salida: {'Sí' if resultado['output_toxicity'] else 'No'}")
        print(f"Costo estimado: ${resultado['estimated_cost_usd']:.5f}")
        print()
