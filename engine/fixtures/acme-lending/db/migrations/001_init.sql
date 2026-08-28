CREATE TABLE borrowers (
  id BIGSERIAL PRIMARY KEY,
  email TEXT NOT NULL,
  full_name TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE applications (
  id BIGSERIAL PRIMARY KEY,
  borrower_id BIGINT NOT NULL REFERENCES borrowers(id),
  amount_cents BIGINT NOT NULL,
  status TEXT NOT NULL,
  submitted_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE decisions (
  id BIGSERIAL PRIMARY KEY,
  application_id BIGINT NOT NULL REFERENCES applications(id),
  model_version TEXT NOT NULL,
  score NUMERIC NOT NULL,
  outcome TEXT NOT NULL,
  decided_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE loans (
  id BIGSERIAL PRIMARY KEY,
  application_id BIGINT NOT NULL REFERENCES applications(id),
  principal_cents BIGINT NOT NULL,
  interest_rate NUMERIC NOT NULL,
  funded_at TIMESTAMPTZ
);

CREATE TABLE payments (
  id BIGSERIAL PRIMARY KEY,
  loan_id BIGINT NOT NULL REFERENCES loans(id),
  amount_cents BIGINT NOT NULL,
  stripe_charge_id TEXT,
  paid_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE audit_events (
  id BIGSERIAL PRIMARY KEY,
  entity TEXT NOT NULL,
  entity_id BIGINT NOT NULL,
  payload TEXT,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_applications_borrower ON applications (borrower_id);
CREATE UNIQUE INDEX idx_borrowers_email ON borrowers (email);
