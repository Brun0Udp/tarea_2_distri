import os, json, asyncio
from typing import Optional
from fastapi import FastAPI, HTTPException
import asyncpg
from confluent_kafka import Producer
from pydantic import BaseModel
from schema import QuestionMsg

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
DATABASE_URL = os.getenv("DATABASE_URL")

app = FastAPI(title="Storage API")

async def get_db():
    return await asyncpg.connect(DATABASE_URL)

producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})

class QueryIn(BaseModel):
    question: str

@app.get("/health")
def health(): return {"ok": True}
async def health():
    return {"ok": True}

@app.post("/query")
async def query(q: QueryIn):
    # 1) Buscar si ya existe con score
    conn = await get_db()
    row = await conn.fetchrow("""
        SELECT id, question, answer_llm, score FROM qa_results
        WHERE question = $1 AND score IS NOT NULL
        ORDER BY decided_at DESC LIMIT 1
    """, q.question)
    await conn.close()

    if row:
        return {"cached": True, "id": str(row["id"]), "answer": row["answer_llm"], "score": float(row["score"])}

    # 2) Encolar para procesamiento
    msg = QuestionMsg.new(q.question)
    producer.produce("questions.new", json.dumps(msg.to_kv()).encode("utf-8"))
    producer.produce("llm.requests", json.dumps(msg.to_kv()).encode("utf-8"))
    producer.flush()
    return {"cached": False, "id": msg.id, "queued": True}

@app.post("/persist")
async def persist(payload: dict):
    # Consumido por Flink → publica aquí via Kafka Connect o llamado directo para simplificar demo:
    conn = await get_db()
    await conn.execute("""
        INSERT INTO qa_results (id, question, answer_llm, score, attempts)
        VALUES ($1,$2,$3,$4,$5)
        ON CONFLICT (id) DO UPDATE SET answer_llm=EXCLUDED.answer_llm, score=EXCLUDED.score, attempts=EXCLUDED.attempts
    """, payload["id"], payload["question"], payload.get("answer_llm"), payload.get("score"), payload.get("attempts", 0))
    await conn.close()
    return {"ok": True}
