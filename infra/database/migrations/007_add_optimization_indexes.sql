-- 007_add_optimization_indexes.sql

-- Snellere screener queries
CREATE INDEX idx_valuations_discount ON valuations(discount_pct);
CREATE INDEX idx_valuations_score ON valuations(score);

-- Snellere relative valuation
CREATE INDEX idx_fundamentals_fcf ON fundamentals(free_cash_flow);
CREATE INDEX idx_fundamentals_debt_equity ON fundamentals(total_debt, total_equity);

-- Snellere prijsqueries
CREATE INDEX idx_prices_close ON prices(close);
