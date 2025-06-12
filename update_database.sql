-- Database update script for improved RAG performance
-- Run this script to add enhanced search capabilities

-- Add full-text search capabilities if not exists
CREATE INDEX IF NOT EXISTS idx_crawled_pages_content_fts ON crawled_pages USING gin(to_tsvector('english', content));

-- Create a composite index for better query performance
CREATE INDEX IF NOT EXISTS idx_crawled_pages_composite ON crawled_pages (url, version, chunk_number);

-- Add index for better similarity filtering
CREATE INDEX IF NOT EXISTS idx_crawled_pages_embedding_similarity ON crawled_pages USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Drop and recreate enhanced search function
DROP FUNCTION IF EXISTS enhanced_match_crawled_pages(vector, integer, float, jsonb);

-- Enhanced search function with similarity threshold and flexible filtering
CREATE OR REPLACE FUNCTION enhanced_match_crawled_pages (
  query_embedding vector(1536),
  match_count int default 10,
  similarity_threshold float default 0.3,
  filter jsonb DEFAULT '{}'::jsonb
) RETURNS TABLE (
  id bigint,
  url varchar,
  chunk_number integer,
  content text,
  metadata jsonb,
  similarity float,
  version integer
)
LANGUAGE plpgsql
AS $$
#variable_conflict use_column
DECLARE
  filter_condition text := '';
  key text;
  value text;
BEGIN
  -- Build dynamic filter conditions for more flexible filtering
  IF filter != '{}'::jsonb THEN
    FOR key, value IN SELECT * FROM jsonb_each_text(filter) LOOP
      IF filter_condition != '' THEN
        filter_condition := filter_condition || ' AND ';
      END IF;
      
      -- Handle different filter types
      IF key = 'source' THEN
        filter_condition := filter_condition || format('metadata->>%L = %L', key, value);
      ELSIF key = 'path' THEN
        filter_condition := filter_condition || format('metadata->>%L = %L', key, value);
      ELSIF key = 'method' THEN
        filter_condition := filter_condition || format('metadata->>%L = %L', key, value);
      ELSIF key = 'section' THEN
        filter_condition := filter_condition || format('metadata->>%L = %L', key, value);
      ELSE
        -- Default: exact match for other metadata fields
        filter_condition := filter_condition || format('metadata->>%L = %L', key, value);
      END IF;
    END LOOP;
  END IF;

  RETURN QUERY EXECUTE format('
    SELECT
      cp.id,
      cp.url,
      cp.chunk_number,
      cp.content,
      cp.metadata,
      1 - (cp.embedding <=> $1) as similarity,
      cp.version
    FROM crawled_pages cp
    WHERE (1 - (cp.embedding <=> $1)) >= $3
    %s
    ORDER BY cp.embedding <=> $1
    LIMIT $2',
    CASE WHEN filter_condition != '' THEN 'AND ' || filter_condition ELSE '' END
  ) USING query_embedding, match_count, similarity_threshold;
END;
$$; 