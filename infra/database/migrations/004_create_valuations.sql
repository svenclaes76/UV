-- 004_create_valuations.sql

CREATE TABLE valuations (
    id SERIAL PRIMARY KEY,
    company_id INT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    valuation_date DATE NOT NULL,
    fair_value NUMERIC(14,4),
    discount_pct NUMERIC(6,3),
    valuation_method TEXT NOT NULL,   -- 'DCF', 'Relative', 'Hybrid'
    score NUMERIC(5,2),
    inputs JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(company_id, valuation_date, valuation_method)
);

CREATE INDEX idx_valuations_company_date
    ON valuations(company_id, valuation_date DESC);
