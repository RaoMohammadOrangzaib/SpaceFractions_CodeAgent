-- SQL DDL for the QuestionComponent's question persistence (ASR-1 durability).
CREATE TABLE questions (
  id TEXT PRIMARY KEY,
  prompt TEXT NOT NULL,
  options JSONB NOT NULL,
  correct_index INTEGER NOT NULL,
  explanation TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
