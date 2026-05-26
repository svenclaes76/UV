# Technical Architecture

This document describes the technical architecture of the application that identifies undervalued stocks using DCF, Relative, and Hybrid valuation models.  
The architecture is modular, scalable, and designed for reliability, performance, and maintainability.

## Application Layers

The system is composed of five main layers:

### Backend API
The backend is built with FastAPI and exposes REST endpoints for the frontend and external consumers.  
It handles business logic, data retrieval, valuation orchestration, and communication with the database.

Key responsibilities:
- Serve screener results
- Provide company metadata
- Expose historical price and fundamentals data
- Return valuation outputs
- Perform health checks

Internal structure:
- Routers for endpoint definitions
- Services for business logic
- Repositories for database access
- Valuation engine integration

### Valuation Engine
The valuation engine contains the core financial logic used to compute intrinsic values.

Modules:
- DCF valuation with cash flow projections and discounting
- Relative valuation using sector benchmarks and multiples
- Hybrid valuation combining DCF and Relative with weighted logic

Outputs:
- Fair value per share
- Discount percentage
- Confidence score
- Model inputs stored as JSON

### ETL Layer
The ETL layer fetches external financial data and loads it into the database.

Processes:
- Price ETL for daily market data
- Fundamentals ETL for quarterly and annual financials
- Company ETL for metadata
- Scheduled valuation jobs for DCF, Relative, and Hybrid models

Features:
- Data validation and normalization
- Idempotent inserts
- Logging of all runs in the jobs_log table

### Database
The database is PostgreSQL and stores all normalized and derived data.

Core tables:
- companies
- fundamentals
- prices
- valuations
- sector_benchmarks
- jobs_log

Characteristics:
- Relational schema optimized for analytical queries
- Indexing for fast screener and valuation lookups
- Referential integrity between entities

### Frontend Web Application
The frontend is built with React and TypeScript and provides a user interface for exploring valuation results.

Features:
- Screener page showing top undervalued stocks
- Filters for sector, valuation method, and score
- Detail page with price history, fair value, and valuation breakdown
- Responsive layout and fast data loading

## Data Flow

The system processes data in the following sequence:

1. ETL jobs fetch external data and load it into PostgreSQL  
2. Valuation jobs compute DCF, Relative, and Hybrid fair values  
3. Results are stored in the valuations table  
4. The backend API exposes the processed data  
5. The frontend displays screener results and stock details  

## Infrastructure

The application is containerized using Docker.  
Services include:
- Backend API container
- Frontend container
- ETL worker container
- PostgreSQL database container

Deployment options:
- Docker Compose for local and small‑scale environments
- Kubernetes for scalable production environments

Monitoring:
- Health endpoints
- ETL run logs
- API structured logging

## Summary

The technical architecture is designed to be:
- Modular, with clear separation of concerns
- Scalable, with independent services for ETL, API, and frontend
- Robust, using multiple valuation models and validated data
- Maintainable, with clean layering and consistent data structures
