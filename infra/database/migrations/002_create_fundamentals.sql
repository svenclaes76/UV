-- 002_create_fundamentals.sql

CREATE TABLE fundamentals (
    id SERIAL PRIMARY KEY,
    company_id INT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    period DATE NOT NULL,
    revenue BIGINT,
    net_income BIGINT,
    ebit BIGINT,
    ebitda BIGINT,
    free_cash_flow BIGINT,
    total_debt BIGINT,
    total_equity BIGINT,
    shares_outstanding BIGINT,
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(company_id, period)
);

CREATE INDEX idx_fundamentals_company_period
    ON fundamentals(company_id, period DESC);
