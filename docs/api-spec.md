# API Specification

This document describes the public API used by the frontend and external clients.  
All endpoints follow REST principles and return JSON responses.

Base URL (example):  
https://api.yourdomain.com

## Screener API

### GET /screener
Returns a ranked list of undervalued stocks based on hybrid valuation.

#### Query Parameters
sector (optional)  
min_score (optional)  
method (optional: DCF, Relative, Hybrid)  
limit (optional, default: 20)

#### Response Example
{
  "count": 20,
  "items": [
    {
      "ticker": "AAPL",
      "price": 175.20,
      "fair_value": 220.50,
      "discount_pct": 0.258,
      "score": 8.7
    }
  ]
}

## Company API

### GET /companies
Returns a list of all companies.

#### Query Parameters
sector (optional)  
country (optional)

### GET /companies/{ticker}
Returns metadata for a single company.

#### Response Fields
ticker  
name  
sector  
industry  
country  
currency  
market_cap  

## Price Data API

### GET /prices/{ticker}
Returns historical daily price data.

#### Query Parameters
start_date (optional)  
end_date (optional)

#### Response Example
{
  "ticker": "AAPL",
  "prices": [
    {
      "date": "2024-01-10",
      "open": 172.10,
      "high": 174.00,
      "low": 171.50,
      "close": 173.80,
      "volume": 51200000
    }
  ]
}

## Valuation API

### GET /valuations/{ticker}
Returns the latest valuation results for a company.

#### Query Parameters
method (optional: DCF, Relative, Hybrid)

#### Response Fields
valuation_date  
fair_value  
discount_pct  
valuation_method  
score  
inputs (JSON)

## Fundamentals API

### GET /fundamentals/{ticker}
Returns historical financial fundamentals.

#### Response Fields
period  
revenue  
net_income  
ebit  
ebitda  
free_cash_flow  
total_debt  
total_equity  
shares_outstanding  

## Health API

### GET /health
Returns the health status of the API.

#### Response Example
{
  "status": "ok",
  "timestamp": "2026-05-26T18:45:00Z"
}

## Error Handling

All errors follow a consistent structure.

#### Error Response Example
{
  "error": "NotFound",
  "message": "Ticker not found",
  "status_code": 404
}

## Summary

The API provides endpoints for screener results, company metadata, price history, fundamentals, valuation outputs, and system health.  
It is designed to be simple, predictable, and optimized for frontend consumption.
