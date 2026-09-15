# Strategic Business Plan: Uvalu.app
*Find value before the market does.*

---

---

## Table of Contents
1. [Executive Summary](#1-executive-summary)
2. [Business Overview](#2-business-overview)
3. [Market Analysis](#3-market-analysis)
4. [Product & Technology](#4-product--technology)
5. [Business Model](#5-business-model)
6. [Go-to-Market Strategy](#6-go-to-market-strategy)
7. [Operations Plan](#7-operations-plan)
8. [Financial Plan](#8-financial-plan)
9. [Risk Analysis](#9-risk-analysis)
10. [Implementation Roadmap](#10-implementation-roadmap)

---

---

## 1. Executive Summary

### Business Concept
**Uvalu.app** is a **cloud-based SaaS platform** that provides **systematic, quantitative stock screening and portfolio management** for **European retail investors**. Built on a **multi-model fair value engine** with **hard veto rules**, Uvalu helps investors identify undervalued stocks while managing risk through a structured, data-driven approach.

### Mission Statement
> *To empower individual investors with institutional-grade valuation tools, enabling them to make disciplined, evidence-based investment decisions.*

### Vision
Become the **#1 value-investing platform for European retail investors** by 2029, recognized for:
- **Accuracy** - Best-in-class fair value estimation
- **Transparency** - Fully documented methodology
- **Trust** - Secure cloud platform with zero data sharing

### Key Differentiators
| Feature | Uvalu | Competitors |
|---------|-------|-------------|
| **Multi-model fair value** | 6 models + fallbacks | Single-model or proprietary black boxes |
| **Hard veto rules** | D/E, FCF, dividend sustainability | Basic filters only |
| **European focus** | 6 major EU exchanges | US-centric or global without EU depth |
| **Risk engine** | 8-stage quantitative assessment | Basic volatility metrics |
| **Privacy** | Secure cloud, encrypted at rest, no data monetization | Cloud-based, data monetization |
| **Cost** | Freemium / low-cost | High subscription fees |

### Financial Snapshot (3-Year Projection from Sept 2026)
| Metric | Year 1 (2027) | Year 2 (2028) | Year 3 (2029) |
|--------|---------------|---------------|---------------|
| **Users** | 10,000 | 50,000 | 200,000 |
| **Revenue (€)** | €240K | €1.2M | €5M |
| **Gross Margin** | 85% | 88% | 90% |
| **Burn Rate** | €100K | €250K | €500K |
| **Break-even** | Q2 2028 | Q1 2029 | Profitable |

### Current Status (September 2026)
- **Product**: Live (v1.9.0), stable, feature-complete MVP
- **Users**: ~5,000 active (organic growth)
- **Revenue**: Early adopters, pre-monetization
- **Team**: 2 founders (CTO + CEO)
- **Infrastructure**: Self-hosted cloud (VPS)

---

---

## 2. Business Overview

### Company Structure
- **Legal Entity**: **Uvalu BV** (Belgium)
- **HQ**: Brussels, Belgium (financial hub, EU regulatory alignment)
- **Team Structure (2026-2029)**:
  - **Founders**: 2 (CTO + CEO)
  - **Year 1 (2027) Hires**: 3 FTE (1 Backend, 1 Frontend, 1 Growth)
  - **Year 2 (2028) Hires**: 5 FTE (+2 Backend, 1 Data Scientist, 1 Support, 1 Marketing)

### Business Type
- **Primary**: **B2C SaaS** (Direct to retail investors only)
- **Focus**: Pure consumer product, no enterprise/B2B/white-label

### Problem Statement
European retail investors face:
1. **Information Overload** - Too many stocks, not enough structured analysis
2. **US Bias** - Most tools focus on US markets (S&P 500, Nasdaq)
3. **Black Box Models** - Proprietary scoring with no transparency
4. **High Costs** - Bloomberg Terminal (€24K/year), Morningstar Premium (€300/year)
5. **Fragmented Tools** - Need separate apps for screening, tracking, and risk

### Solution
Uvalu provides:
- European-first coverage (Brussels, Amsterdam, Paris, Milan, Frankfurt, Swiss)
- 6-model fair value engine (Graham, PE Fair Value, EPV, DDM, Analyst Target, Book Value)
- 8-stage risk assessment (Concentration, Volatility, VaR, Factor Exposure, Stress Tests, Monte Carlo)
- Secure cloud platform (Encrypted at rest, no data sharing)
- Freemium model (Free tier for screening, paid for advanced features)

---

---

## 3. Market Analysis

### Target Market
#### Primary: Retail Investors (Europe)
- **Total Addressable Market (TAM)**: **50M** active retail investors in EU
- **Serviceable Available Market (SAM)**: **5M** self-directed investors (use screening tools)
- **Serviceable Obtainable Market (SOM)**: **200K** users in 3 years (4% of SAM)

### Market Segmentation
| Segment | Size (EU) | Pain Points | Uvalu Fit |
|---------|-----------|-------------|-----------|
| **DIY Investors** | 3M | Need systematic screening | Core product |
| **Dividend Investors** | 1M | Need income sustainability checks | Risk engine |
| **Value Investors** | 500K | Need fair value models | 6-model engine |
| **Young Investors** | 2M | Need education + low cost | Freemium |

### Competitive Landscape
| Competitor | Strengths | Weaknesses | Uvalu Advantage |
|------------|-----------|------------|------------------|
| **Morningstar** | Brand recognition, analyst reports | US-focused, expensive, black box | EU focus, transparent, affordable |
| **TradingView** | Global coverage, charting | No fundamental screening | Deep fundamentals, fair value |
| **Simply Wall St** | Visual reports, global | No EU exchange depth | 6 EU exchanges, local data |
| **Bloomberg Terminal** | Institutional-grade | €24K/year, steep learning curve | 1% of cost, intuitive UX |
| **Portfolio Visualizer** | Backtesting, risk tools | US-only, no screening | EU + screening + risk |
| **Yahoo Finance** | Free, global | No screening, no risk | Full pipeline |

### SWOT Analysis
| **Strengths** | **Weaknesses** |
|---------------|----------------|
| EU-first coverage | New brand (no recognition) |
| Transparent methodology | Limited marketing budget |
| Secure cloud platform | Small team (scalability risk) |
| Multi-model engine | No mobile app (yet) |
| Open-source roots (trust) | Dependency on yfinance (data) |

| **Opportunities** | **Threats** |
|-------------------|-------------|
| Growing EU retail investor base | Regulatory changes (MiFID III) |
| FinTech adoption in Europe | Competition from incumbents |
| Open banking / PSD3 | Data provider costs |
| Community-driven growth | Economic downturn (lower demand) |

### Market Trends
1. **Rise of Retail Investing in EU**
   - 2020-2026: **25% CAGR** in EU retail trading (ESMA)
   - **20M new investors** in Europe since COVID
2. **Demand for Transparency**
   - 78% of investors prefer **open methodology** (2024 Deloitte Survey)
3. **Cloud Adoption**
   - 85% of retail investors comfortable with **secure cloud tools** (2026 Statista)
4. **Value Investing Resurgence**
   - Post-2022: **40% increase** in value fund inflows (Morningstar)

---

---

## 4. Product & Technology

### Core Product Offering
| Feature | Description | Status |
|---------|-------------|--------|
| **Screener** | Multi-exchange stock ranking with 6-stage valuation | Live |
| **Portfolio Tracker** | Real-time P&L, dividends, benchmarks | Live |
| **Dashboard** | KPIs, charts, risk snapshot | Live |
| **Risk Engine** | 8-stage quantitative assessment | Live |
| **Stock Analysis** | Deep-dive per stock | Live |
| **Multi-User Auth** | JWT-based, role-based access | Live |
| **Backup/Restore** | Encrypted cloud backups | Live |
| **Admin Portal** | User management, settings | Live |
| **Mobile App** | iOS/Android (React Native) | Q3 2027 |
| **API Access** | REST API for power users | Q1 2028 |

### Technology Stack
| Layer | Technology | Rationale |
|-------|------------|-----------|
| **Frontend** | Streamlit (Python) | Fast iteration, no JS needed |
| **Backend** | Python (FastAPI) | Scalable, data science friendly |
| **Data** | yfinance (Yahoo Finance) | Free, reliable, global coverage |
| **Database** | PostgreSQL (Cloud) | ACID-compliant, scalable |
| **Auth** | JWT + bcrypt | Secure, stateless |
| **Encryption** | AES-256 (Fernet) | FIPS-compliant, secure |
| **Cloud Provider** | AWS (Frankfurt region) | GDPR-compliant, scalable |
| **Deployment** | Docker + Kubernetes | Scalable, resilient |
| **CI/CD** | GitHub Actions | Automated testing, releases |
| **Monitoring** | Sentry + Prometheus | Observability, alerts |

### Product Roadmap
| Phase | Timeline | Key Features |
|-------|----------|--------------|
| **Current (Sept 2026)** | Now | Core screening, portfolio, risk, multi-user |
| **Phase 1** | Q1 2027 | Mobile app (React Native), monetization |
| **Phase 2** | Q3 2027 | API access, backtesting, tax optimization |
| **Phase 3** | Q1 2028 | AI insights (LLM-powered), social features |
| **Phase 4** | Q3 2028 | Advanced analytics, community features |

### Intellectual Property
- **Trademark**: "Uvalu" (EU)
- **Copyright**: All code, documentation, branding
- **Open Source**: Core engine (MIT License) to build trust

---

---

## 5. Business Model

### Revenue Streams
| Stream | Description | Pricing | Launch |
|--------|-------------|---------|--------|
| **Freemium** | Basic screening (100 stocks/month), 1 portfolio | Free | Now |
| **Pro** | Full screening, portfolio tracking, basic risk | €9.99/month | Q1 2027 |
| **Premium** | Advanced risk, backtesting, API access (1000 calls/day) | €24.99/month | Q3 2027 |
| **Affiliate** | Brokerage referrals (0.1% of trades) | Revenue share | Q2 2027 |

### Pricing Strategy
| Tier | Price (Monthly) | Price (Annual) | Features |
|------|------------------|----------------|----------|
| **Free** | €0 | €0 | 100 stocks/month, 1 portfolio, basic charts |
| **Pro** | €9.99 | €99 (17% off) | Unlimited stocks, 5 portfolios, full risk, mobile app |
| **Premium** | €24.99 | €249 (17% off) | Backtesting, API access, priority support, advanced analytics |

### Customer Acquisition Cost (CAC)
| Channel | CAC (€) | Expected Conversion | LTV (€) |
|---------|---------|---------------------|---------|
| **Organic (SEO)** | €5 | 2% | €288 |
| **Content Marketing** | €20 | 3% | €288 |
| **Paid Ads (Google/FB)** | €50 | 1% | €288 |
| **Affiliate** | €30 | 2% | €288 |
| **Referral** | €10 | 5% | €288 |

**Target LTV:CAC Ratio**: **5:1** (Industry benchmark: 3:1)

### Churn & Retention
| Metric | Target | Industry Avg. |
|--------|--------|---------------|
| **Monthly Churn** | 3% | 5-8% |
| **Annual Churn** | 25% | 40-60% |
| **Retention (12M)** | 60% | 40% |
| **NPS** | 50+ | 30-40 |

---

---

## 6. Go-to-Market Strategy

### Launch Phases
| Phase | Timeline | Goals | Tactics |
|-------|----------|-------|---------|
| **Current (Sept 2026)** | Now | 5,000 users | Organic growth, beta testing |
| **Monetization** | Q1 2027 | 10,000 users | Pro tier launch, referral program |
| **Growth** | Q3 2027 | 50,000 users | Paid ads, partnerships, SEO |
| **Scale** | Q1 2028 | 200,000 users | Mobile app, API, community features |

### Marketing Channels
#### 1. Organic (Low Cost, High ROI)
- **SEO**:
  - Target keywords: _"best stock screener Europe"_, _"undervalued stocks Europe"_, _"portfolio risk calculator"_
  - Blog: Weekly deep-dives on value investing in EU
- **Content Marketing**:
  - YouTube: Tutorials, stock analysis walkthroughs
  - Newsletter: Monthly market insights + Uvalu updates
- **Community**:
  - Reddit (r/Investing, r/FinancialIndependenceEU)
  - Discord server for power users

#### 2. Paid (Scalable)
- **Google Ads**: Target _"stock screener"_, _"portfolio tracker"_, _"value investing"_
- **Facebook/Instagram**: Retargeting, lookalike audiences
- **LinkedIn**: Thought leadership

#### 3. Partnerships
- **Brokers**: Integrate Uvalu as a "Research" tab (revenue share)
- **Financial Bloggers**: Sponsored content, affiliate links

#### 4. Referral Program
- **Incentive**: €10 credit for referrer + referee
- **Viral Coefficient Target**: 1.2 (Each user brings 1.2 new users)

### Brand Positioning
| Dimension | Uvalu | Competitors |
|-----------|-------|-------------|
| **For** | Systematic investors | Traders, speculators |
| **Who want** | Undervalued stocks with low risk | Quick gains, momentum |
| **Unlike** | Bloomberg (expensive), TradingView (US-focused) | **Uvalu is EU-first, transparent, affordable** |
| **We offer** | Institutional-grade tools for retail | Black-box, high-cost solutions |

### Messaging
- **Tagline**: _"Find value before the market does."_
- **Elevator Pitch**:
  > _"Uvalu is a cloud-based stock screener and portfolio tracker built for European value investors. Unlike US-focused tools, we cover 6 major EU exchanges with a 6-model fair value engine and 8-stage risk assessment—all with a secure, privacy-first cloud platform. No black boxes, no data monetization, just disciplined investing."_

---

---

## 7. Operations Plan

### Development Workflow
- **Methodology**: Agile (2-week sprints)
- **Tools**:
  - GitHub (Code, Issues, Projects)
  - Linear (Roadmap)
  - Figma (Design)
  - Notion (Documentation)

### Infrastructure (Cloud-Based)
| Component | Provider | Cost (Monthly, 2027) | Cost (Monthly, 2028) |
|-----------|----------|---------------------|---------------------|
| **Hosting** | AWS (Frankfurt) | €500 | €2,000 |
| **Database** | AWS RDS (PostgreSQL) | €200 | €800 |
| **Storage** | AWS S3 (Encrypted) | €50 | €200 |
| **CI/CD** | GitHub Actions | €0 (Free tier) | €100 |
| **Monitoring** | Sentry + Prometheus | €100 | €300 |
| **Email** | SendGrid | €20 | €50 |
| **Total** | | **€870** | **€3,450** |

### Team Structure
| Role | Responsibilities | Hire Date |
|------|------------------|-----------|
| **CEO** | Strategy, fundraising, partnerships | Now |
| **CTO** | Product, engineering, architecture | Now |
| **Backend Dev** | Core engine, API, data pipelines | Q1 2027 |
| **Frontend Dev** | Streamlit, UI/UX, mobile | Q1 2027 |
| **Growth Marketer** | SEO, ads, partnerships | Q2 2027 |
| **Data Scientist** | Model improvements, analytics | Q3 2027 |
| **Support** | Customer support, community | Q4 2027 |

### Key Processes
1. **Feature Development**:
   - Idea -> Spec -> Design -> Dev -> Test -> Beta -> Release
2. **Customer Support**:
   - Email (support@uvalu.app)
   - Discord (Community)
   - Intercom (Live chat, 2028)
3. **Data Pipeline**:
   - Daily: Stock prices, dividends
   - Weekly: Fundamentals refresh
   - Monthly: Risk model recalibration

---

---

## 8. Financial Plan

### Startup Costs (2026-2027)
| Category | Cost (€) |
|----------|----------|
| **Legal (Registration, Trademarks, GDPR)** | 10,000 |
| **Cloud Infrastructure (First Year)** | 10,000 |
| **Design (Logo, Branding, UI/UX)** | 5,000 |
| **Development (Contractors, Mobile App)** | 30,000 |
| **Marketing (Launch Campaigns)** | 20,000 |
| **Miscellaneous** | 5,000 |
| **Total** | **€80,000** |

### Revenue Projections (2027-2029)
| Metric | 2027 | 2028 | 2029 |
|--------|------|------|------|
| **Users (Free)** | 7,000 | 35,000 | 140,000 |
| **Users (Paid)** | 3,000 | 15,000 | 60,000 |
| **ARPU (Monthly)** | €12 | €15 | €18 |
| **Revenue (€)** | €432K | €2.7M | €12.96M |
| **Gross Margin** | 85% | 88% | 90% |
| **Operating Costs** | €300K | €800K | €2M |
| **Net Profit** | **(€132K)** | **€1.1M** | **€9.3M** |
| **Cash Burn** | €100K | €250K | €500K |

### Funding Requirements
| Round | Amount (€) | Use of Funds | Timeline |
|-------|------------|--------------|----------|
| **Seed** | €500K | Team, marketing, cloud scaling | Q4 2026 |
| **Series A** | €5M | Expansion, mobile, international | Q2 2028 |

### Key Financial Metrics
| Metric | 2027 | 2028 | 2029 |
|--------|------|------|------|
| **CAC (€)** | 40 | 30 | 25 |
| **LTV (€)** | 288 | 360 | 432 |
| **LTV:CAC** | 7:1 | 12:1 | 17:1 |
| **Churn (Monthly)** | 5% | 3% | 2% |
| **MRR Growth** | 25% | 40% | 50% |

### Break-Even Analysis
- **Monthly Burn Rate**: €25K (2027), €70K (2028)
- **Users Needed for Break-Even**:
  - **2027**: ~2,100 paid users (€25K MRR)
  - **2028**: ~4,700 paid users (€70K MRR)
- **Expected Break-Even**: **Q2 2028**

---

---

## 9. Risk Analysis

### Business Risks
| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Low Adoption** | Medium | High | Aggressive marketing, partnerships |
| **Competition** | High | Medium | Differentiate (EU focus, transparency) |
| **Regulatory Changes** | Medium | High | Legal compliance, early engagement with EU regulators |
| **Data Provider Issues** | Medium | High | Multi-source fallback, caching, direct data feeds |
| **Technical Downtime** | Low | High | Redundant hosting, monitoring, SLA guarantees |
| **Funding Shortfall** | Medium | High | Bootstrapping, revenue-first approach |

### Technical Risks
| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **yfinance API Changes** | Medium | High | Local caching, alternative providers (Alpha Vantage, Twelve Data) |
| **Scalability Issues** | Medium | Medium | Microservices, load testing, auto-scaling |
| **Security Breaches** | Low | Critical | Penetration testing, encryption, GDPR compliance |
| **Data Accuracy** | Medium | High | Validation, user feedback loops, multi-source verification |

### Market Risks
| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Economic Downturn** | Medium | Medium | Freemium model, essential features, cost optimization |
| **Shift to Passive Investing** | Low | Medium | Education on active value investing, performance tracking |
| **Privacy Regulation (GDPR)** | Medium | High | Cloud-first with GDPR compliance, data processing agreements |

---

---

## 10. Implementation Roadmap

### Q4 2026 (Pre-Launch Scaling)
- [ ] Finalize monetization strategy (Pro/Premium tiers)
- [ ] Legal setup (GDPR compliance, terms of service)
- [ ] Seed funding (€500K)
- [ ] Cloud infrastructure scaling (AWS migration)
- [ ] Alpha testing (5,000 users)

### Q1 2027 (Monetization Launch)
- [ ] Launch Pro tier (€9.99/month)
- [ ] Launch referral program
- [ ] Hire first 2 developers (Backend + Frontend)
- [ ] SEO optimization
- [ ] Content marketing (Blog, YouTube)

### Q2 2027 (Growth Acceleration)
- [ ] Launch Premium tier (€24.99/month)
- [ ] Affiliate program launch
- [ ] Hire Growth Marketer
- [ ] Paid ads (Google, Facebook)
- [ ] Partnerships (Financial bloggers)

### Q3 2027 (Product Expansion)
- [ ] Mobile app launch (iOS/Android)
- [ ] API access (Premium feature)
- [ ] Backtesting tool
- [ ] First 10,000 paid users

### Q4 2027 (Scale Preparation)
- [ ] Tax optimization features
- [ ] Community features (Discord integration)
- [ ] Hire Data Scientist + Support
- [ ] 50,000 total users

### 2028 (Scale Phase)
- [ ] AI insights (LLM-powered stock analysis)
- [ ] Social features (Shared watchlists)
- [ ] Advanced analytics
- [ ] Series A prep (€5M)
- [ ] 200,000 total users

### 2029 (Maturity Phase)
- [ ] International expansion (UK, Nordics)
- [ ] Advanced risk models
- [ ] Automated portfolio rebalancing
- [ ] Profitability

---

---

## Appendices

### A. Product Screenshots (Concept)
1. **Dashboard** - Portfolio snapshot with KPIs, charts, holdings
2. **Screener** - Filterable list of undervalued stocks across 6 EU exchanges
3. **Stock Analysis** - Deep-dive into a single stock's valuation with 6-model breakdown
4. **Risk Assessment** - 8-stage risk breakdown with actionable insights
5. **Mobile App** - Streamlined for on-the-go investing

### B. Competitor Deep Dive
| Competitor | Pricing | EU Coverage | Screening | Risk Tools | Privacy | Cloud/Local |
|------------|---------|-------------|-----------|------------|---------|------------|
| Morningstar | €300/year | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ❌ Data monetization | Cloud |
| TradingView | €15/month | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ❌ Data monetization | Cloud |
| Simply Wall St | €10/month | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ❌ Data monetization | Cloud |
| Portfolio Visualizer | Free | ⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ✅ No monetization | Cloud |
| **Uvalu** | **€10-25/month** | **⭐⭐⭐⭐⭐** | **⭐⭐⭐⭐⭐** | **⭐⭐⭐⭐⭐** | **✅ No monetization** | **Cloud (GDPR-compliant)** |

### C. Customer Personas
1. **Dirk (Value Investor, 45, Netherlands)**
   - **Goal**: Find undervalued Dutch/Belgian stocks
   - **Pain**: No good EU-focused screener with transparent methodology
   - **Uvalu Fit**: 6-model fair value, 6 EU exchanges, hard veto rules

2. **Sophie (Dividend Investor, 35, France)**
   - **Goal**: Build a passive income portfolio with sustainable dividends
   - **Pain**: Hard to assess dividend sustainability and income risk
   - **Uvalu Fit**: Dividend risk scoring, income concentration analysis

3. **Hans (Young Investor, 28, Germany)**
   - **Goal**: Learn value investing without expensive tools
   - **Pain**: Overwhelmed by too many stocks, high costs of alternatives
   - **Uvalu Fit**: Free tier, educational content, intuitive UI

4. **Luca (Part-Time Investor, 40, Italy)**
   - **Goal**: Manage portfolio efficiently with limited time
   - **Pain**: Fragmented tools for screening, tracking, and risk
   - **Uvalu Fit**: All-in-one platform, mobile app, automated insights

### D. Glossary
- **MoS (Margin of Safety)**: % difference between fair value and market price
- **HHI (Herfindahl-Hirschman Index)**: Measure of portfolio concentration
- **VaR (Value at Risk)**: Maximum expected loss over a time period at a given confidence level
- **DDM (Dividend Discount Model)**: Stock valuation based on future dividends
- **EPV (Earnings Power Value)**: Stock valuation based on normalized earnings
- **GDPR**: General Data Protection Regulation (EU privacy law)

### E. References
- [Uvalu GitHub Repository](https://github.com/svenclaes76/UV)
- [Stock Valuation Algorithm Docs](docs/stock_valuation_algorithm.md)
- [Portfolio Risk Assessment Docs](docs/portfolio_risk_assessment_algorithm.md)
- [Architecture Overview](docs/architecture.md)
- [Configuration Reference](docs/configuration.md)

---

---

## Conclusion
Uvalu.app is positioned to **disrupt the European retail investing space** by offering a **transparent, EU-focused, secure cloud-based** alternative to bloated, US-centric, or black-box tools. With a **strong technical foundation**, **clear differentiation**, and a **scalable business model**, Uvalu can achieve **€5M+ revenue and 200K users by 2029**.

**Next Steps (Q4 2026)**:
1. **Secure Seed Funding** (€500K)
2. **Launch Monetization** (Pro/Premium tiers)
3. **Scale Infrastructure** (AWS migration)
4. **Build Team** (First 2 hires)
5. **Accelerate Growth** (Marketing, partnerships)

> _"The stock market is designed to transfer money from the Active to the Patient. Uvalu helps you be both."_

---
**Document Version**: 2.0
**Last Updated**: September 2026
**Prepared by**: Uvalu Strategy Team
**Contact**: [uvalu.app@gmail.com](mailto:uvalu.app@gmail.com) | [uvalu.app](https://uvalu.app)
