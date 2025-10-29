CREATE TABLE IF NOT EXISTS qa_results (
  id UUID PRIMARY KEY,
  question TEXT NOT NULL,
  answer_llm TEXT,
  score NUMERIC,
  attempts INT DEFAULT 0,
  decided_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_qa_results_question ON qa_results USING GIN (to_tsvector('simple', question));
