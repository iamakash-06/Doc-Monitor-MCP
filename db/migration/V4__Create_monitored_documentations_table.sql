-- Create_monitored_documentations_table
-- Created by setup_flyway.py

CREATE TABLE IF NOT EXISTS monitored_documentations (
    id BIGSERIAL PRIMARY KEY,
    url VARCHAR NOT NULL UNIQUE,
    name VARCHAR(255),
    description TEXT,
    status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    last_checked_at TIMESTAMP WITH TIME ZONE,
    check_frequency_hours INTEGER DEFAULT 24,
    notes TEXT
);
