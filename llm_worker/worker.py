import os, json, time, random, sys
from confluent_kafka import Consumer, Producer
from schema import LLMResponseMsg  


BOOTSTRAP      = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
GROUP_ID       = os.getenv("GROUP_ID", "worker_llm")
IN_TOPIC       = os.getenv("KAFKA_TOPIC_IN", "preguntas")          
OUT_TOPIC      = os.getenv("KAFKA_TOPIC_OUT", "llm_respuestas")   
RETRY_TOPIC    = os.getenv("KAFKA_RETRY_TOPIC", IN_TOPIC + ".retry")
DLQ_TOPIC      = os.getenv("KAFKA_DLQ_TOPIC", "dlq")

MAX_OVERLOAD   = int(os.getenv("MAX_OVERLOAD_RETRIES", "5"))
MAX_QUOTA      = int(os.getenv("MAX_QUOTA_RETRIES", "3"))
USE_REAL       = os.getenv("USE_REAL_LLM", "false").lower() == "true"
LOG_LEVEL      = os.getenv("LOG_LEVEL", "INFO")

producer = Producer({"bootstrap.servers": BOOTSTRAP})
cons = Consumer({
    "bootstrap.servers": BOOTSTRAP,
    "group.id": GROUP_ID,
    "auto.offset.reset": "earliest",
  
})

cons.subscribe([IN_TOPIC])

def log(*args):
    if LOG_LEVEL.upper() == "DEBUG":
        print("[DEBUG]", *args, file=sys.stderr, flush=True)

def mock_llm_answer(question: str) -> str:
    r = random.random()
    if r < 0.10:
        raise RuntimeError("overload") 
    if r < 0.13:
        raise RuntimeError("quota")    
    return f"Respuesta mock para: {question}"

def call_real_llm(question: str) -> str:
    # TODO: implementa aquí tu proveedor real
    # ejemplo de “stub” para no romper:
    return mock_llm_answer(question)

def handle_retry(msg_value: dict, kind: str, attempt: int, max_attempts: int, base_sleep: float):
    if attempt >= max_attempts:
        msg_value["error"] = kind
        msg_value["final"] = True
        producer.produce(DLQ_TOPIC, json.dumps(msg_value).encode("utf-8"))
        producer.flush()
        log(f"DLQ ({kind}) id={msg_value.get('id')} attempt={attempt}")
        return
 
    time.sleep(base_sleep)
    msg_value["attempt"] = attempt + 1
    msg_value["origin"] = kind
 
    target = RETRY_TOPIC or IN_TOPIC
    producer.produce(target, json.dumps(msg_value).encode("utf-8"))
    producer.flush()
    log(f"retry→{target} ({kind}) id={msg_value.get('id')} next_attempt={attempt+1}")

try:
    log(f"BOOTSTRAP={BOOTSTRAP} GROUP_ID={GROUP_ID} IN={IN_TOPIC} RETRY={RETRY_TOPIC} OUT={OUT_TOPIC} DLQ={DLQ_TOPIC}")
    while True:
        msg = cons.poll(1.0)
        if msg is None:
            continue
        if msg.error():
            log("Kafka message error:", msg.error())
            continue

        try:
            data = json.loads(msg.value().decode("utf-8"))
        except Exception as e:
         
            producer.produce(DLQ_TOPIC, json.dumps({"raw": msg.value().decode("utf-8","ignore"), "error": "bad_json"}).encode("utf-8"))
            producer.flush()
            log("bad_json sent to DLQ")
            continue

        q = data.get("question")
        if not q:
         
            data["error"] = "missing_question"
            producer.produce(DLQ_TOPIC, json.dumps(data).encode("utf-8"))
            producer.flush()
            log("missing_question → DLQ")
            continue

        attempt = int(data.get("attempt", 0))
        try:
            answer = call_real_llm(q) if USE_REAL else mock_llm_answer(q)
            out = {
                "id": data.get("id"),
                "question": q,
                "answer": answer,
                "attempt": attempt
            }

            producer.produce(OUT_TOPIC, json.dumps(out).encode("utf-8"))
            producer.flush()
            log(f"OK → {OUT_TOPIC} id={out['id']}")
        except RuntimeError as e:
            kind = str(e)
            if kind == "overload":
                handle_retry(data, "overload", attempt, MAX_OVERLOAD, base_sleep=2 ** min(attempt, 5))
            elif kind == "quota":
                handle_retry(data, "quota", attempt, MAX_QUOTA, base_sleep=60.0)
            else:
                data["error"] = f"unknown:{kind}"
                producer.produce(DLQ_TOPIC, json.dumps(data).encode("utf-8"))
                producer.flush()
                log(f"unknown error → DLQ id={data.get('id')}")
        except Exception as e:
            
            data["error"] = f"exception:{type(e).__name__}"
            producer.produce(DLQ_TOPIC, json.dumps(data).encode("utf-8"))
            producer.flush()
            log(f"exception → DLQ id={data.get('id')} ex={e}")
finally:
    cons.close()
