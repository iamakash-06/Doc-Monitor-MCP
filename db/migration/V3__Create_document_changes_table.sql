-- Create_document_changes_table
-- Created by setup_flyway.py

CREATE TABLE IF NOT EXISTS document_changes (
    id BIGSERIAL PRIMARY KEY,
    url VARCHAR NOT NULL,
    old_content_hash VARCHAR(64),
    new_content_hash VARCHAR(64) NOT NULL,
    change_type VARCHAR(50) NOT NULL,
    detected_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb
);
