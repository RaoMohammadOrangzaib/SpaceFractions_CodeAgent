-- QuestionComponent data model (ASR-1: data durability)
CREATE TABLE questions (
  id TEXT PRIMARY KEY,
  prompt TEXT NOT NULL,
  options JSONB NOT NULL,
  correct_answer TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
