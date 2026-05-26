# Stock Valuation and Screener Platform

This application identifies undervalued stocks using three valuation models: Discounted Cash Flow (DCF), Relative Valuation, and Hybrid Valuation. It provides a complete pipeline from data ingestion to valuation computation and frontend visualization.

## Features

Automated ETL pipelines for prices, fundamentals, and company metadata  
DCF, Relative, and Hybrid valuation models  
Screener ranking system for identifying undervalued stocks  
REST API built with FastAPI  
React frontend with screener and stock detail pages  
PostgreSQL database with normalized financial data  
Docker-based deployment  

## Technical Architecture

The system consists of five main components.

### Backend API
FastAPI service that exposes endpoints for screener results, company metadata, historical prices, fundamentals, and valuation outputs.  
Implements routers, services, repositories, and integrates the valuation engine.

### Valuation Engine
Implements three valuation models:  
DCF valuation with cash flow projections and discounting  
Relative valuation using sector benchmarks  
Hybrid valuation combining both models with weighted logic  

### ETL Layer
Scheduled jobs that fetch and load:  
Daily price data  
Quarterly and annual fundamentals  
Company metadata  
Sector benchmarks  
Automated valuation runs  

### Database
PostgreSQL schema containing:  
companies  
fundamentals  
prices  
valuations  
sector_benchmarks  
jobs_log  

### Frontend Web Application
React and TypeScript interface with:  
Screener table  
Filters for sector, valuation method, and score  
Stock detail pages  
Price versus fair value charts  

## Data Sources

External market data for prices and volumes  
External fundamentals for financial statements  
Company metadata including sector and industry  
Sector benchmark multiples  
Internally derived valuation results  

## Valuation Models

### DCF Valuation
Five-year cash flow projections  
Terminal value  
Discounting using WACC or fixed rate  

### Relative Valuation
Sector comparison using P/E, EV/EBITDA, and FCF yield  

### Hybrid Valuation
Weighted combination of DCF and Relative  
Default weighting: 60 percent DCF, 40 percent Relative  

## API Overview

Key endpoints include:  
GET /screener  
GET /companies  
GET /companies/{ticker}  
GET /prices/{ticker}  
GET /fundamentals/{ticker}  
GET /valuations/{ticker}  
GET /health  

## Development Setup

Requirements:  
Python  
Node.js  
PostgreSQL  
Docker (optional)

Steps:  
Install backend dependencies  
Install frontend dependencies  
Set up PostgreSQL schema  
Run ETL jobs to populate data  
Start backend and frontend services  

## Docker Deployment

The project includes Docker configurations for backend, frontend, ETL worker, and PostgreSQL.  
All services can be started together using Docker Compose.

## Project Structure

backend  
frontend  
etl  
database  
docs  

## License

Add your preferred license in a LICENSE file.

## Contributing

Contributions are welcome. Follow the coding style and documentation standards.

## Contact

For questions or suggestions, contact the project maintainer.
