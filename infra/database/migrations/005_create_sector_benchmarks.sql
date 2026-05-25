-- 005_create_sector_benchmarks.sql

CREATE TABLE sector_benchmarks (
    id SERIAL PRIMARY KEY,
    sector TEXT NOT NULL,
    period DATE NOT NULL,
    pe_avg NUMERIC(8,3),
    ev_ebitda_avg NUMERIC(8,3),
    pb_avg NUMERIC(8,3),
    fcf_yield_avg NUMERIC(8,3),
    UNIQUE(sector, period)
);

CREATE INDEX idx_sector_benchmarks_sector
    ON sector_benchmarks(sector);
