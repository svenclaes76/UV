# 🏗️ Architecture Overview

This document provides a high‑level overview of the system architecture for the platform that identifies undervalued stocks using DCF, Relative, and Hybrid valuation methods.  
It serves as the starting point for developers, analysts, and contributors who need to understand how the system is structured.

---

## 1. System Components

The system consists of five major components:

- **Backend API** — FastAPI service exposing data and valuation results.
- **Valuation Engine** — Core logic for DCF, Relative, and Hybrid valuation.
- **ETL Layer** — Pipelines that fetch, clean, and load external financial data.
- **Database** — PostgreSQL storing companies, prices, fundamentals, and valuations.
- **Frontend Webapp** — React application providing screener and stock detail views.

---

## 2. Backend API

The backend provides:

- Screener endpoint (top undervalued stocks)
- Company metadata
- Historical price data
- Valuation results (DCF, Relative, Hybrid)
- Health checks

### Structure

- Routers — define API endpoints  
- Services — business logic and orchestration  
- Repositories — database access  
- Valuation Engine — invoked by services  

The backend acts as the central hub between ETL, database, and frontend.

---

## 3. Valuation Engine

The valuation engine contains three modules:

### DCF Module
- 5‑year cash flow projections  
- Terminal value  
- Discounting (WACC or fixed rate)  
- Fair value per share  

### Relative Valuation
- Sector benchmark comparison  
- P/E, EV/EBITDA, FCF‑yield metrics  

### Hybrid Valuation
- Weighted combination of DCF and Relative  
- Default: 60% DCF / 40% Relative  
- Auto‑rebalance if one method is missing  

All results are stored in the `valuations` table.

---

## 4. ETL Layer

The ETL layer fetches external data and loads it into the database.

### ETL Processes

- Prices ETL — daily closing prices  
- Fundamentals ETL — quarterly and annual financials  
- Companies ETL — metadata such as sector and industry  
- Valuation Jobs — run DCF, Relative, Hybrid for all companies  

### Scheduling

- Cron, Airflow, or Dagster  
- All runs logged in `jobs_log`  

The ETL layer ensures the system always has fresh, validated data.

---

## 5. Database

The PostgreSQL schema includes:

- companies  
- fundamentals  
- prices  
- valuations  
- sector_benchmarks  
- jobs_log  

### Relationships

- A company has many fundamentals  
- A company has many price records  
- A company has many valuation results  
- Sector benchmarks are used during valuation  

The schema is optimized for fast screening, valuation lookups, and historical analysis.

---

## 6. Frontend Webapp

The frontend is built with React + TypeScript and includes:

- Screener Page — top undervalued stocks  
- Filters — sector, score, valuation method  
- Detail Page — price vs fair value chart, valuation breakdown  
- Routing and layout  

The UI is designed to be fast, intuitive, and data‑driven.

---

## 7. Deployment & Infrastructure

- Docker containers for backend, frontend, ETL, and PostgreSQL  
- Docker Compose for MVP; Kubernetes for scaling  
- Logging via `jobs_log` and structured API logs  
- Monitoring via health endpoints and ETL metrics  

---

## 8. Data Flow Summary

1. ETL fetches external data (prices, fundamentals, companies)  
2. Valuation engine runs DCF, Relative, Hybrid  
3. Results stored in `valuations`  
4. Backend API exposes screener and detail endpoints  
5. Frontend displays results in tables and charts  

---

## 9. Summary

The architecture is:

- Modular — clear separation of concerns  
- Scalable — ETL, API, and frontend operate independently  
- Robust — Hybrid valuation + sector benchmarks  
- Production‑ready — logging, monitoring, jobs, database design  
