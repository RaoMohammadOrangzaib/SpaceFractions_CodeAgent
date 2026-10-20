-- SQL DDL for the GameComponent's persisted game state.
-- Mirrors the JSON-file persistence used by the running service (ASR-1 durability).
CREATE TABLE games (
  id SERIAL PRIMARY KEY,
  game_state JSONB NOT NULL
);

-- Additional table for structured game sessions (score etc.).
CREATE TABLE game_sessions (
  id TEXT PRIMARY KEY,
  score INTEGER NOT NULL DEFAULT 0,
  total_answered INTEGER NOT NULL DEFAULT 0,
  question_ids JSONB NOT NULL,
  current_question_index INTEGER NOT NULL DEFAULT 0,
  finished BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
