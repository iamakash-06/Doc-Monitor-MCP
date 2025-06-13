-- Create_indexes
-- Created by setup_flyway.py

-- Indexes for crawled_pages
CREATE INDEX IF NOT EXISTS idx_crawled_pages_url ON crawled_pages(url);
CREATE INDEX IF NOT EXISTS idx_crawled_pages_source ON crawled_pages(source);
CREATE INDEX IF NOT EXISTS idx_crawled_pages_endpoint ON crawled_pages(endpoint);
CREATE INDEX IF NOT EXISTS idx_crawled_pages_method ON crawled_pages(method);
CREATE INDEX IF NOT EXISTS idx_crawled_pages_created_at ON crawled_pages(created_at);

-- Indexes for document_changes  
CREATE INDEX IF NOT EXISTS idx_document_changes_url ON document_changes(url);
CREATE INDEX IF NOT EXISTS idx_document_changes_detected_at ON document_changes(detected_at);

-- Indexes for monitored_documentations
CREATE INDEX IF NOT EXISTS idx_monitored_docs_status ON monitored_documentations(status);
CREATE INDEX IF NOT EXISTS idx_monitored_docs_last_checked ON monitored_documentations(last_checked_at);
