# R&D Role Profiles

14 Oct 2026 · Profiles of the in-house R&D roles needed to grow Uvalu into a multi-user SaaS. Use them for hiring and for reviewing the team plan. Outside advisors (lawyers, auditors, testers) are in [../experts/](../experts/README.md). Salary estimates are kept out of the repo on purpose.

## How to read these profiles

Each profile describes the expert you want in the seat: the mission, experience, core skills, stack, first-90-day outputs, success metrics, interview signals and red flags. Stack examples assume a Python-first SaaS (FastAPI or Django, Postgres, React/Next.js, EU-hosted AWS or GCP). That is a natural next step from the current Streamlit codebase. Swap tools where your stack differs.

| Role | Stage | Seniority to hire | Experience |
| --- | --- | --- | --- |
| Product Manager | MVP | Senior | 5+ yrs, 2+ in B2B/B2C SaaS |
| Tech Lead / Architect | MVP | Staff / Senior | 8+ yrs |
| Full-stack / Backend Engineer | MVP | Mid to Senior | 3–7 yrs |
| Frontend Engineer | MVP | Mid to Senior | 3–6 yrs |
| UX/UI Designer | MVP (part-time) | Senior | 5+ yrs |
| DevOps / Platform / SRE | Growth | Senior | 5+ yrs |
| QA / Test Automation | Growth | Mid to Senior | 3–6 yrs |
| Data Engineer | Growth (earlier for data products) | Senior | 5+ yrs |
| Data Scientist / Analyst | Growth | Mid to Senior | 3–6 yrs |
| Security Engineer | Growth | Senior | 6+ yrs |
| Engineering Manager | Growth (8+ engineers) | Senior | 7+ yrs, 2+ managing |
| Mobile, ML, Solutions, Tech Writer, Release Mgr, CTO | Scale | Varies | See below |
| Quant / Financial Analyst, Compliance Advisor | MVP for uvalu | Senior | 5+ yrs domain |

## Product Manager / Product Owner

Mission: decide what gets built and why, so every sprint moves a measurable business outcome.

| Dimension | Profile |
| --- | --- |
| Background | 5+ years in product, 2+ owning a SaaS product end to end. Ideally ex-engineer, analyst or fintech domain specialist. |
| Core expertise | Customer discovery and jobs-to-be-done interviews. Prioritization frameworks (RICE, opportunity scoring). Pricing and packaging. Writing crisp PRDs and user stories. |
| Tools | Linear or Jira, Notion or Confluence, Figma (reading level), Amplitude or PostHog, SQL for self-serve analysis. |
| First 90 days | 15–20 customer interviews. A ranked problem list. A 2-quarter roadmap. A North Star metric and activation definition. |
| Success metrics | Activation rate, trial-to-paid conversion, net revenue retention, feature adoption, roadmap hit rate. |
| Interview signals | Kills their own ideas with data. Can explain a trade-off they made and what it cost. Asks about users before solutions. |
| Red flags | Roadmap as a feature list with dates. No metrics attached to past launches. Writes specs engineers cannot estimate. |

## Tech Lead / Software Architect

Mission: design a system the team can ship fast on today and still scale in two years, then lead by writing code.

| Dimension | Profile |
| --- | --- |
| Background | 8+ years building production web systems, 2+ as tech lead on a multi-tenant SaaS. Has taken a product from prototype to paying customers. |
| Core expertise | Multi-tenant architecture and data isolation. API design (REST, OpenAPI). Postgres data modelling. Auth (OAuth2/OIDC). Billing integration. Caching and background jobs. Pragmatic modular monolith over premature microservices. |
| Tools | Python (FastAPI/Django), Postgres, Redis, Celery or Temporal, Docker, Terraform, GitHub Actions, Stripe, Auth0/Clerk/Keycloak. |
| First 90 days | Architecture decision records for the core choices. Migration plan from Streamlit prototype to SaaS. CI pipeline, coding standards, and a working auth + billing skeleton. |
| Success metrics | Lead time for changes, deployment frequency, change failure rate, p95 latency, unplanned rework. |
| Interview signals | Draws the system and names its weakest point unprompted. Explains a decision they reversed. Still ships code weekly. |
| Red flags | Reaches for Kubernetes and microservices on day one. Cannot explain cost implications. Designs without talking to product. |

## Full-stack / Backend Engineer

Mission: turn product requirements into reliable, tested APIs and business logic that customers depend on daily.

| Dimension | Profile |
| --- | --- |
| Background | 3–7 years in backend or full-stack development, at least one SaaS product in production. |
| Core expertise | Python (typing, async, packaging). SQL and query optimization. REST API design. Background jobs and scheduling. Third-party integrations (payments, market data APIs, email). Unit and integration testing. |
| Tools | FastAPI or Django, SQLAlchemy, Alembic, Postgres, Redis, pytest, Docker, Sentry, basic React for full-stack profiles. |
| First 90 days | Ships a customer-facing feature end to end. Adds tests to an untested area. Owns one integration (e.g. a market data provider or Stripe). |
| Success metrics | Cycle time per story, escaped defects, test coverage on owned modules, on-call incident count. |
| Interview signals | Writes readable code with tests in a pairing exercise. Asks about edge cases and failure modes. Explains a production bug they debugged. |
| Red flags | No testing habit. Cannot reason about N+1 queries or indexes. Blames others for past outages. |

## Frontend Engineer

Mission: build a fast, accessible interface that makes dense financial data easy to scan and act on.

| Dimension | Profile |
| --- | --- |
| Background | 3–6 years building production web apps, ideally data-heavy dashboards or fintech tools. |
| Core expertise | TypeScript and React. State and server-cache management. Data grids and charting at scale. Web performance (Core Web Vitals). WCAG 2.2 accessibility. Design-system implementation. |
| Tools | Next.js or Vite, TanStack Query/Table, Tailwind, a chart library (ECharts, Recharts or D3), Storybook, Playwright, Vitest. |
| First 90 days | Component library aligned with the designer. Rebuild of the screener and portfolio views. Frontend error and performance monitoring. |
| Success metrics | Largest Contentful Paint < 2.5 s, interaction latency, accessibility audit score, UI defect rate. |
| Interview signals | Discusses rendering 10,000-row tables without jank. Thinks about empty, loading and error states. Shows a polished portfolio piece. |
| Red flags | Ignores accessibility. Over-engineers state. Cannot work from a Figma spec without hand-holding. |

## UX/UI Designer

Mission: make complex investing workflows feel simple, and prove it with user testing.

| Dimension | Profile |
| --- | --- |
| Background | 5+ years in product design, 2+ on SaaS or data-dense tools. Fintech or analytics experience is a strong plus. |
| Core expertise | User research and usability testing. Information architecture. Interaction design for tables, filters and charts. Design systems. Onboarding and conversion flows. |
| Tools | Figma (components, variables, prototyping), Maze or Lyssna, Dovetail, FigJam, basic HTML/CSS literacy. |
| First 90 days | Usability test of the current app with 5–8 users. Core design system (type, colour, components). Redesigned onboarding and screener flow. |
| Success metrics | Task success rate, time-to-first-insight, onboarding completion, System Usability Scale score. |
| Interview signals | Case study shows research, rejected options and measured outcome, not only final screens. Comfortable designing for numbers. |
| Red flags | Portfolio of visuals with no problem statement. Resists constraints from engineering. Never tests with real users. |

## DevOps / Platform / SRE

Mission: make shipping safe and boring, keep the service up, and keep the cloud bill proportional to revenue.

| Dimension | Profile |
| --- | --- |
| Background | 5+ years in DevOps, SRE or platform engineering on customer-facing SaaS with on-call duty. |
| Core expertise | Infrastructure as code. CI/CD with automated rollback. Containers and orchestration. Observability (metrics, logs, traces). SLOs and error budgets. Incident management. FinOps. Backup and disaster recovery. |
| Tools | Terraform or Pulumi, AWS or GCP (EU regions), Docker, ECS or Kubernetes, GitHub Actions, Grafana/Prometheus or Datadog, OpenTelemetry, PagerDuty, Vault or cloud secrets manager. |
| First 90 days | All infra in code. Staging and production environments. One-click deploys. Dashboards and alerts for core SLOs. A tested restore from backup. |
| Success metrics | Availability vs SLO (e.g. 99.9%), mean time to recovery, deployment frequency, cloud cost per active customer. |
| Interview signals | Walks through a real incident and its blameless postmortem. Talks about cost as readily as uptime. Automates themselves out of toil. |
| Red flags | Click-ops habits. Alert fatigue as normal. Gold-plates infra beyond the stage of the company. |

## QA / Test Automation Engineer

Mission: catch defects before customers do, by building automated quality gates the whole team trusts.

| Dimension | Profile |
| --- | --- |
| Background | 3–6 years in QA with strong automation, ideally SDET-style on a SaaS team shipping weekly or faster. |
| Core expertise | Test strategy and the test pyramid. End-to-end and API test automation. Test data management. Regression and release gating. Exploratory testing. Numeric-accuracy checks for financial calculations. |
| Tools | Playwright, pytest, Postman or Schemathesis, k6 for load, GitHub Actions, Allure or similar reporting. |
| First 90 days | Test strategy document. Smoke and critical-path E2E suite in CI. Golden-dataset tests for valuation metrics. Flaky-test policy. |
| Success metrics | Escaped defects per release, critical-path coverage, suite runtime < 10 min, flaky-test rate. |
| Interview signals | Writes maintainable automation in a live exercise. Pushes quality left into design and code review. Finds edge cases in a spec quickly. |
| Red flags | Manual-only background. Sees QA as a gate at the end rather than a shared practice. Tolerates flaky tests. |

## Data Engineer

Mission: deliver accurate, timely, licensed market and fundamentals data that the product and analytics can trust.

| Dimension | Profile |
| --- | --- |
| Background | 5+ years building production data pipelines. Financial market data experience (prices, fundamentals, corporate actions) is a major plus. |
| Core expertise | Batch and incremental ingestion. Data modelling (star schema, slowly changing dimensions). Data quality and lineage. Handling corporate actions, currencies and point-in-time data. Vendor API and licence management. |
| Tools | Python, SQL, dbt, Dagster or Airflow, Postgres, DuckDB or BigQuery/Snowflake, Great Expectations or Soda, Parquet. |
| First 90 days | Inventory of data sources and licence terms. Orchestrated, monitored ingestion pipeline. Data quality checks with alerting. Documented data model. |
| Success metrics | Data freshness vs SLA, pipeline success rate, data-quality incidents, cost per data refresh. |
| Interview signals | Explains how they handled a stock split or a restated filing. Designs for backfills and idempotency. Thinks about vendor lock-in. |
| Red flags | Scrapes data without checking licence terms. No data tests. Pipelines that cannot be re-run safely. |

## Data Scientist / Analyst

Mission: answer the business's hardest questions with data, and turn analytical models into product features.

| Dimension | Profile |
| --- | --- |
| Background | 3–6 years in product analytics or applied data science. A quantitative degree (statistics, economics, physics, CS). Finance exposure helps for in-product models. |
| Core expertise | Product analytics (funnels, cohorts, retention). Experiment design and A/B testing. Statistical modelling. Factor or scoring models for in-product rankings. Clear communication of uncertainty. |
| Tools | SQL, Python (pandas, polars, scikit-learn, statsmodels), Jupyter, PostHog or Amplitude, a BI tool (Metabase, Looker or Superset). |
| First 90 days | Event tracking plan. Core KPI dashboard (activation, retention, revenue). First experiment shipped. Review of the scoring logic in the screener. |
| Success metrics | Decisions influenced, experiment velocity, dashboard adoption, accuracy of in-product models vs backtests. |
| Interview signals | Explains a result that surprised them and how they checked it. Knows when not to run a test. Translates numbers into a recommendation. |
| Red flags | P-hacking or no notion of statistical power. Dashboards nobody uses. Models with no validation. |

## Security Engineer

Mission: protect customer financial data and earn the trust (and certifications) that enterprise buyers require.

| Dimension | Profile |
| --- | --- |
| Background | 6+ years in application or cloud security, ideally in a SaaS or fintech company that went through SOC 2 or ISO 27001. |
| Core expertise | Threat modelling. Secure SDLC and code review. OWASP Top 10 and API security. Cloud IAM and network hardening. Secrets management. Vulnerability management. GDPR and DORA awareness. Audit evidence collection. |
| Tools | Semgrep or CodeQL, Dependabot or Snyk, Trivy, cloud security posture tools, Vault, Vanta or Drata, Burp Suite. |
| First 90 days | Threat model of the core app. Automated SAST, dependency and container scanning in CI. Access review and MFA everywhere. Roadmap to SOC 2 Type I. |
| Success metrics | Time to remediate critical vulns, findings per pentest, audit readiness, security incidents. |
| Interview signals | Pragmatic risk-based prioritization. Builds guardrails developers like using. Explains a breach they investigated. |
| Red flags | Says "no" without offering a safer path. Compliance checklists without real controls. No hands-on technical depth. |

## Engineering Manager

Mission: build a team that ships predictably and keeps its best people, so the tech lead can stay technical.

| Dimension | Profile |
| --- | --- |
| Background | 7+ years in engineering, 2+ managing 5–10 engineers. Has hired at least 5 people and handled a performance problem. |
| Core expertise | Hiring and onboarding. 1:1s, feedback and career ladders. Agile delivery and planning. Cross-team coordination with product and design. Managing technical debt as a business trade-off. |
| Tools | Linear or Jira, a delivery-metrics tool (LinearB, Swarmia or DORA dashboards), Lattice or Culture Amp, Greenhouse or Ashby. |
| First 90 days | 1:1s with every engineer. Hiring plan and structured interview loop. Delivery cadence with visible metrics. A career ladder draft. |
| Success metrics | Delivery predictability, regretted attrition, time-to-hire, engagement score, DORA metrics trend. |
| Interview signals | Concrete stories of growing someone and of a tough conversation. Measures outcomes, not hours. Credible technical judgment. |
| Red flags | Micro-manages tickets. Shields the team from all context. Has never fired or managed out an underperformer. |

## Scale-stage roles

These six roles come after the core team is working well. They are shown in one table because each is hired later and needs a shorter profile.

| Role | Background | Core expertise and tools | Success metrics | Key interview signal | Red flag |
| --- | --- | --- | --- | --- | --- |
| Mobile Engineer | 4+ yrs shipping iOS/Android apps with real users | React Native or Flutter (or Swift/Kotlin), offline sync, push notifications, app store releases | Crash-free sessions > 99.5%, store rating, mobile retention | Has shipped and maintained an app through several OS releases | Web-only experience labelled as mobile |
| ML Engineer | 4+ yrs putting ML models into production | Python, PyTorch or scikit-learn, feature stores, model serving, MLflow, monitoring for drift; LLM integration | Model latency, drift alerts handled, uplift vs baseline | Talks about monitoring and rollback, not only accuracy | Notebook-only work, no production story |
| Solutions / Integration Engineer | 4+ yrs in customer-facing technical roles in B2B SaaS | APIs, SSO/SAML, data exports, scripting, technical demos, scoping | Time-to-integration, deal win rate with SE involvement, CSAT | Explains a complex integration to a non-technical buyer | Promises custom work the product cannot support |
| Technical Writer | 3+ yrs writing developer and end-user docs | Docs-as-code (Markdown, Docusaurus or Mintlify), OpenAPI, information architecture | Support tickets deflected, doc search success, API onboarding time | Writing sample that is short, accurate and task-oriented | Marketing tone in technical docs |
| Release Manager | 5+ yrs coordinating releases across several teams | Release trains, feature flags (LaunchDarkly/Unleash), change management, release notes | On-time releases, rollback rate, change failure rate | Reduces process overhead while increasing safety | Adds approval gates that slow every team |
| CTO / Head of Engineering | 12+ yrs, 5+ leading engineering orgs of 20–100 | Technical strategy, org design, budgeting, board communication, vendor and build-vs-buy decisions | Delivery against company goals, engineering cost as % of revenue, retention of senior engineers | Has scaled an org through at least one doubling | Wants to rewrite everything on arrival |

### Technical Writer

Mission: make the product and its API self-explanatory, so customers succeed without opening a support ticket.

| Dimension | Profile |
| --- | --- |
| Background | 3+ years writing developer and end-user documentation for a SaaS product. Experience with API docs is required. Familiarity with finance or investing terminology is a plus for uvalu. |
| Core expertise | Task-based help articles and tutorials. API reference and quickstarts. Information architecture and search-friendly structure. Plain-language explanations of metrics and methodology. Style guides and terminology control. Release notes. |
| Tools | Docs-as-code (Markdown, Git, Docusaurus or Mintlify), OpenAPI/Swagger, Vale for style linting, Figma (reading level), screenshot and GIF tools, Intercom or Zendesk help centre. |
| First 90 days | Docs audit and information architecture. Getting-started guide and screener/portfolio how-tos. Methodology pages for each valuation metric, reviewed by the quant analyst. Style guide and release-note template. |
| Success metrics | Support tickets deflected, doc search success rate, time to first API call, page feedback score, docs updated within one release of a feature change. |
| Interview signals | Writing sample that is short, accurate and task-oriented. Rewrites a confusing paragraph live and explains the cuts. Interviews engineers efficiently and verifies by running the steps. |
| Red flags | Marketing tone in technical docs. Copies specs without testing them. Treats docs as a one-off project rather than part of each release. |

## Domain roles for uvalu

A European stock screener needs two domain experts early, often as part-time advisors before full-time hires.

### Quant / Financial Domain Analyst

Mission: make sure every valuation metric, score and risk figure in the app is correct and defensible.

| Dimension | Profile |
| --- | --- |
| Background | 5+ years in equity research, quantitative investing or portfolio analytics. CFA charterholder or progress is a plus. |
| Core expertise | Valuation (DCF, multiples, quality and value factors). IFRS financial statements. European market specifics (exchanges, currencies, dividends, tax). Backtesting and avoiding look-ahead and survivorship bias. Portfolio risk metrics. |
| Tools | Python (pandas, numpy), SQL, Excel, market data terminals or APIs, backtesting frameworks. |
| First 90 days | Audit of every metric in the screener and risk pages. Golden test dataset with hand-checked values. Methodology documentation for users. |
| Success metrics | Metric errors found in production, methodology coverage, user trust signals (support questions on numbers). |
| Interview signals | Spots an error in a sample calculation. Explains how a metric breaks for banks or insurers. |
| Red flags | Purely theoretical background. Overclaims backtest results. |

### Compliance & Regulatory Advisor

Mission: keep the product on the right side of investment-advice, data-protection and consumer rules across the EU.

| Dimension | Profile |
| --- | --- |
| Background | 5+ years in fintech or investment-services compliance, or a regulatory lawyer with fintech clients. |
| Core expertise | MiFID II (investment advice vs information), ESMA guidance on financial content, GDPR, DORA for ICT risk, marketing rules for financial products, market data licensing. |
| Tools | Policy and register templates, Vanta or Drata for evidence, contract review. |
| First 90 days | Regulatory assessment of the screener and portfolio features. Disclaimers and terms of service. GDPR records of processing and DPA templates. |
| Success metrics | Regulatory findings, time to approve new features, zero unplanned licence breaches. |
| Interview signals | Gives practical "how we can ship this" answers, not only risks. Knows the advice-vs-information line in detail. |
| Red flags | Blocks features without alternatives. Only knows one national regime. |
