import os, time, random, requests

STORAGE = os.getenv("STORAGE_API_URL", "http://storage_api:8000")
QPM = int(os.getenv("QPM", "10"))
TOTAL = int(os.getenv("TOTAL_QUERIES", "50"))
SLEEP = 60.0 / max(QPM,1)

SEED_QUESTIONS = [
    "¿Cómo resetear contraseña en Ubuntu 22.04?",
    "¿Qué es un árbol B+ en bases de datos?",
    "¿Diferencia entre TCP y UDP?",
    "¿Cómo funciona un balanceador de carga?",
    "¿Qué es backpressure en sistemas de streaming?",
    "¿Cómo calcular latencia p95 en un sistema?",
]

for i in range(TOTAL):
    q = random.choice(SEED_QUESTIONS)
    r = requests.post(f"{STORAGE}/query", json={"question": q}, timeout=10)
    print(f"[{i+1}/{TOTAL}] {q} -> {r.json()}")
    time.sleep(SLEEP)
