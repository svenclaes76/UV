-- 006_create_jobs_log.sql

CREATE TABLE jobs_log (
    id SERIAL PRIMARY KEY,
    job_name TEXT NOT NULL,
    run_at TIMESTAMP DEFAULT NOW(),
    status TEXT NOT NULL,       -- 'success', 'error'
    message TEXT
);

CREATE INDEX idx_jobs_log_job_name
    ON jobs_log(job_name);
