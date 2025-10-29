import os
import json
import re
import signal
import sys
import unicodedata
from time import time
from typing import Iterable, Optional, Set, Any, Dict

from confluent_kafka import Consumer, Producer, KafkaError

# ---------- Config ----------
BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
GROUP_ID = os.getenv("GROUP_ID", "flink_like_job_g1")
AUTO_OFFSET_RESET = os.getenv("AUTO_OFFSET_RESET", "earliest")

TOPIC_IN = os.getenv("TOPIC_IN", "responses.ok")           # ejemplos: responses.ok | llm_respuestas
TOPIC_PERSIST = os.getenv("TOPIC_PERSIST", "storage.persist")
TOPIC_DLQ = os.getenv("TOPIC_DLQ", "dlq")
TOPIC_RETRY = os.getenv("TOPIC_RETRY", "questions.retry")  # ejemplos: questions.retry | preguntas.pendientes
TOPIC_LLM_REQ = os.getenv("TOPIC_LLM_REQ", "llm.requests")

THRESH = float(os.getenv("SCORE_THRESHOLD", "0.62"))
MAX_SCORE_RETRIES = int(os.getenv("MAX_SCORE_RETRIES", "2"))
ENABLE_EXACT_COMMIT = os.getenv("ENABLE_EXACT_COMMIT", "true").lower() == "true"

# ---------- Kafka clients ----------
cons = Consumer({
    "bootstrap.servers": BOOTSTRAP,
    "group.id": GROUP_ID,
    "auto.offset.reset": AUTO_OFFSET_RESET,
    "enable.auto.commit": not ENABLE_EXACT_COMMIT,  # si haremos commit manual, desactiva auto
})
cons.subscribe([TOPIC_IN])

# delivery report
def _dr(err, msg):
    if err is not None:
        print(f"[PROD] Error entregando a {msg.topic()}: {err}", file=sys.stderr)

prod = Producer({"bootstrap.servers": BOOTSTRAP})

# ---------- Helpers ----------
def _first(d: Dict[str, Any], keys: Iterable[str], default=None):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default

def _strip_accents(s: str) -> str:
    # normaliza: útil si preguntas/respuestas vienen con tildes
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch)
    )

TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9áéíóúÁÉÍÓÚñÑ]+")

def tokenize(s: Optional[str]) -> Set[str]:
    if not s:
        return set()
    s = _strip_accents(s.lower())
    return set(TOKEN_PATTERN.findall(s))

def score_answer(question: str, answer: str) -> float:
    # proxy simple Jaccard entre tokens
    a = tokenize(question)
    b = tokenize(answer)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)

_running = True
def _graceful(*_):
    global _running
    _running = False
    print("\n[SYS] Señal recibida, cerrando...")

signal.signal(signal.SIGINT, _graceful)
signal.signal(signal.SIGTERM, _graceful)

print(f"[CFG] BOOTSTRAP={BOOTSTRAP} TOPIC_IN={TOPIC_IN} PERSIST={TOPIC_PERSIST} DLQ={TOPIC_DLQ} RETRY={TOPIC_RETRY} LLM_REQ={TOPIC_LLM_REQ}")
print(f"[CFG] THRESH={THRESH} MAX_SCORE_RETRIES={MAX_SCORE_RETRIES} GROUP_ID={GROUP_ID} AUTO_OFFSET_RESET={AUTO_OFFSET_RESET}")
print("[RUN] Esperando mensajes...")

try:
    while _running:
        msg = cons.poll(1.0)
        prod.poll(0)  # sirve delivery reports en background

        if msg is None:
            continue

        if msg.error():
            if msg.error().code() != KafkaError._PARTITION_EOF:
                print(f"[CONS] Error: {msg.error()}", file=sys.stderr)
            continue

        try:
            payload = json.loads(msg.value().decode("utf-8"))
        except Exception as e:
            # si llega basura, mejor a DLQ con razón
            prod.produce(
                TOPIC_DLQ,
                json.dumps({"raw": msg.value().decode("utf-8", "ignore"), "reason": "invalid_json", "error": str(e)}).encode("utf-8"),
                callback=_dr,
            )
            continue

        # Campo id
        _id = _first(payload, ["id", "uuid", "msg_id"])
        # Pregunta: acepta "question", "pregunta", "q"
        q = _first(payload, ["question", "pregunta", "q"], "")
        # Respuesta del LLM: "answer", "respuesta", "a", "text"
        ans = _first(payload, ["answer", "respuesta", "a", "text"], "")
        # Intentos: "attempt", "intentos", "retries", "try"
        attempts = int(_first(payload, ["attempt", "intentos", "retries", "try"], 0))

        if not _id or not q:
            # Mensaje no usable -> DLQ
            prod.produce(
                TOPIC_DLQ,
                json.dumps({"payload": payload, "reason": "missing_id_or_question"}).encode("utf-8"),
                callback=_dr,
            )
            if ENABLE_EXACT_COMMIT:
                cons.commit(message=msg, asynchronous=False)
            continue

        score = score_answer(q, ans or "")
        decision = "accept" if score >= THRESH else "retry"

        if decision == "accept":
            out = {
                "id": _id,
                "question": q,
                "answer_llm": ans,
                "score": score,
                "attempts": attempts,
                "processed_at": int(time() * 1000),
                "source_topic": TOPIC_IN,
            }
            prod.produce(TOPIC_PERSIST, json.dumps(out).encode("utf-8"), callback=_dr)
        else:
            if attempts >= MAX_SCORE_RETRIES:
                prod.produce(
                    TOPIC_DLQ,
                    json.dumps({**payload, "score": score, "reason": "low_score_maxed"}).encode("utf-8"),
                    callback=_dr,
                )
            else:
                requeued = {
                    "id": _id,
                    "question": q,
                    "attempt": attempts + 1,
                    "origin": "score_low",
                    "created_at": int(time() * 1000),
                }
                # opcional: un solo topic si tu pipeline vuelve a consumir desde ahí,
                # o dos si separas "reintentar planificación" y "disparar LLM"
                prod.produce(TOPIC_RETRY, json.dumps(requeued).encode("utf-8"), callback=_dr)
                prod.produce(TOPIC_LLM_REQ, json.dumps(requeued).encode("utf-8"), callback=_dr)

        if ENABLE_EXACT_COMMIT:
            cons.commit(message=msg, asynchronous=False)

    print("[SYS] Saliendo del loop principal...")
finally:
    try:
        prod.flush(10)
    except Exception:
        pass
    cons.close()
    print("[SYS] Kafka cerrado.")
