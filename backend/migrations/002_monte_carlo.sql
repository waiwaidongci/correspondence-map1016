-- 002: conditional Monte Carlo test runs with fixed row/column margins.
-- Counters, out-of-order pending batches and the in-flight ledger are stored as JSON so the
-- merge rule can guarantee identical stopping positions to a same-seed sequential run.
-- Source fingerprint invalidates runs when the underlying table changes; stale results stay readable.
CREATE TABLE IF NOT EXISTS monte_carlo_runs (
 id BIGSERIAL PRIMARY KEY,
 study_id BIGINT NOT NULL REFERENCES contingency_studies(id),
 name VARCHAR(100) NOT NULL,
 seed INTEGER NOT NULL,
 epsilon DOUBLE PRECISION NOT NULL,
 min_draws INTEGER NOT NULL,
 max_draws INTEGER NOT NULL,
 batch_size INTEGER NOT NULL,
 status VARCHAR(20) NOT NULL DEFAULT 'queued',
 result JSON NOT NULL DEFAULT '{}'::json,
 error VARCHAR(1000),
 source_fingerprint VARCHAR(64) NOT NULL,
 is_stale BOOLEAN NOT NULL DEFAULT FALSE,
 stale_reason VARCHAR(200),
 ledger JSON NOT NULL DEFAULT '{}'::json,
 pending_batches JSON NOT NULL DEFAULT '{}'::json,
 in_flight JSON NOT NULL DEFAULT '{}'::json,
 stop_index INTEGER,
 creator_id BIGINT NOT NULL REFERENCES users(id),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_monte_carlo_runs_study ON monte_carlo_runs(study_id);
CREATE INDEX IF NOT EXISTS idx_monte_carlo_runs_status ON monte_carlo_runs(status);
