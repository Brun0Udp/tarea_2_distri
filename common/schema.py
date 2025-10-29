from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any
import uuid, time

def now_ms() -> int:
    return int(time.time() * 1000)

@dataclass
class QuestionMsg:
    id: str
    question: str
    attempt: int = 0
    origin: str = "new"
    created_at: int = now_ms()

    @staticmethod
    def new(q: str) -> "QuestionMsg":
        return QuestionMsg(id=str(uuid.uuid4()), question=q)

    def to_kv(self) -> Dict[str, Any]:
        return {"id": self.id, "question": self.question, "attempt": self.attempt,
                "origin": self.origin, "created_at": self.created_at}

@dataclass
class LLMResponseMsg:
    id: str
    question: str
    answer: Optional[str]
    error: Optional[str] = None
    attempt: int = 0
    created_at: int = now_ms()
