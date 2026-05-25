-- 003_create_prices.sql

CREATE TABLE prices (
    id SERIAL PRIMARY KEY,
    company_id INT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    open NUMERIC(12,4),
    high NUMERIC(12,4),
    low NUMERIC(12,4),
    close NUMERIC(12,4),
    volume BIGINT,
    UNIQUE(company_id, date)
);

CREATE INDEX idx_prices_company_date
    ON prices(company_id, date DESC);
