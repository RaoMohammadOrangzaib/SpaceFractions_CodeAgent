-- GameComponent data model (ASR-1: data durability)
CREATE TABLE games (
  id SERIAL PRIMARY KEY,
  game_state JSONB NOT NULL,
  score INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
