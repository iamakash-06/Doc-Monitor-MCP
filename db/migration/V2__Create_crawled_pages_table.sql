-- Create_crawled_pages_table
-- Created by setup_flyway.py

CREATE TABLE IF NOT EXISTS crawled_pages (
    id BIGSERIAL PRIMARY KEY,
    url VARCHAR NOT NULL,
    chunk_number INTEGER NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding VECTOR(1536),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    source VARCHAR(255),
    endpoint VARCHAR(255),
    method VARCHAR(10)
);
