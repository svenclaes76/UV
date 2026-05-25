-- 001_create_companies.sql

CREATE TABLE companies (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(12) UNIQUE NOT NULL,
    name TEXT NOT NULL,
    sector TEXT,
    industry TEXT,
    country TEXT,
    currency CHAR(3) DEFAULT 'USD',
    market_cap BIGINT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_companies_sector ON companies(sector);
