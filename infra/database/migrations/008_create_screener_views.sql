-- 008_create_screener_views.sql

CREATE VIEW screener_latest AS
SELECT
    c.ticker,
    c.name,
    v.fair_value,
    p.close AS current_price,
    v.discount_pct,
    v.score,
    v.valuation_method,
    v.valuation_date
FROM valuations v
JOIN companies c ON c.id = v.company_id
JOIN prices p ON p.company_id = c.id
WHERE v.valuation_date = (
    SELECT MAX(v2.valuation_date)
    FROM valuations v2
    WHERE v2.company_id = v.company_id
)
AND p.date = (
    SELECT MAX(p2.date)
    FROM prices p2
    WHERE p2.company_id = p.company_id
);
