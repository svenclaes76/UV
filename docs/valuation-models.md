# 📐 Valuation Models Overview

This document provides an overview of the valuation models used in the platform to determine the intrinsic value of stocks.  
The system uses three complementary approaches: DCF, Relative Valuation, and Hybrid Valuation.

---

## 1. Discounted Cash Flow (DCF)

### Purpose
DCF estimates the intrinsic value of a company by projecting future free cash flows and discounting them back to present value.

### Key Inputs
- Free cash flow (historical and projected)
- Revenue and margin growth assumptions
- Terminal growth rate
- Discount rate (WACC or fixed rate)
- Shares outstanding

### Method Summary
- Project free cash flows for five years  
- Calculate terminal value using perpetual growth  
- Discount all cash flows to present value  
- Divide by shares outstanding to obtain fair value per share  

### Strengths
- Based on fundamentals  
- Long‑term focused  
- Useful for stable cash‑generating companies  

### Limitations
- Sensitive to assumptions  
- Requires reliable fundamentals data  

---

## 2. Relative Valuation

### Purpose
Relative valuation compares a company to its sector or industry peers using financial multiples.

### Key Multiples
- Price‑to‑Earnings (P/E)
- EV/EBITDA
- Price‑to‑Book (P/B)
- Free Cash Flow Yield

### Method Summary
- Retrieve sector benchmark multiples  
- Compare company metrics to sector averages  
- Estimate fair value based on how the company should be priced relative to peers  

### Strengths
- Simple and intuitive  
- Useful when cash flow projections are uncertain  
- Reflects market sentiment  

### Limitations
- Dependent on peer group quality  
- Can be distorted by market overvaluation or undervaluation  

---

## 3. Hybrid Valuation

### Purpose
Hybrid valuation combines DCF and Relative Valuation to produce a more balanced and robust fair value estimate.

### Weighting
- Default: 60% DCF and 40% Relative  
- Automatically rebalances if one method is unavailable  

### Method Summary
- Compute DCF fair value  
- Compute Relative fair value  
- Apply weighting to generate hybrid fair value  
- Store result in the valuations table  

### Strengths
- Reduces reliance on a single model  
- More stable across different market conditions  
- Works well for companies with mixed characteristics  

### Limitations
- Still depends on quality of underlying models  
- Weighting may need tuning for certain sectors  

---

## 4. Derived Metrics

### Discount Percentage
Measures how undervalued or overvalued a stock is relative to its fair value.

Formula:  
`(Fair Value – Current Price) / Current Price`

### Screener Score
Composite ranking metric combining:
- Discount percentage  
- Model confidence  
- Data completeness  
- Sector consistency  

Used to rank stocks in the screener.

---

## Summary

The platform uses three valuation models:

1. **DCF** — fundamental, long‑term, cash‑flow based  
2. **Relative** — peer‑based, market‑driven  
3. **Hybrid** — weighted combination for robustness  

Together, these models provide a balanced and reliable assessment of intrinsic value across different types of companies.
