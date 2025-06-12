-- Enable the pgvector extension
create extension if not exists vector;

-- Create the documentation chunks table
create table crawled_pages (
    id bigserial primary key,
    url varchar not null,
    chunk_number integer not null,
    content text not null,  -- Added content column
    metadata jsonb not null default '{}'::jsonb,  -- Added metadata column
    embedding vector(1536),  -- OpenAI embeddings are 1536 dimensions
    created_at timestamp with time zone default timezone('utc'::text, now()) not null,
    version integer not null default 1,  -- Added version tracking
    last_modified_at timestamp with time zone default timezone('utc'::text, now()) not null,
    
    -- Add a unique constraint to prevent duplicate chunks for the same URL
    unique(url, chunk_number, version)
);

-- Create a table to track document changes
create table document_changes (
    id bigserial primary key,
    url varchar not null,
    version integer not null,
    change_type varchar not null,  -- 'added', 'modified', 'deleted'
    change_summary text not null,
    change_impact varchar not null,  -- Changed from text to varchar to match function return type
    change_details jsonb not null default '{}'::jsonb,
    created_at timestamp with time zone default timezone('utc'::text, now()) not null,
    
    -- Add a unique constraint to prevent duplicate change records
    unique(url, version)
);

-- Create an index for better vector similarity search performance
create index on crawled_pages using ivfflat (embedding vector_cosine_ops);

-- Create an index on metadata for faster filtering
create index idx_crawled_pages_metadata on crawled_pages using gin (metadata);

CREATE INDEX idx_crawled_pages_source ON crawled_pages ((metadata->>'source'));

-- Create an index for version tracking
CREATE INDEX idx_crawled_pages_version ON crawled_pages (url, version);

-- Add full-text search capabilities
CREATE INDEX idx_crawled_pages_content_fts ON crawled_pages USING gin(to_tsvector('english', content));

-- Create a composite index for better query performance
CREATE INDEX idx_crawled_pages_composite ON crawled_pages (url, version, chunk_number);

-- Add index for better similarity filtering
CREATE INDEX idx_crawled_pages_embedding_similarity ON crawled_pages USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Drop existing functions if they exist
DROP FUNCTION IF EXISTS match_crawled_pages(vector, integer, jsonb);
DROP FUNCTION IF EXISTS get_latest_version(varchar);
DROP FUNCTION IF EXISTS compare_document_versions(varchar, integer, integer);
DROP FUNCTION IF EXISTS enhanced_match_crawled_pages(vector, integer, float, jsonb);

-- Create a function to search for documentation chunks
create or replace function match_crawled_pages (
  query_embedding vector(1536),
  match_count int default 10,
  filter jsonb DEFAULT '{}'::jsonb
) returns table (
  id bigint,
  url varchar,
  chunk_number integer,
  content text,
  metadata jsonb,
  similarity float,
  version integer
)
language plpgsql
as $$
#variable_conflict use_column
begin
  return query
  select
    id,
    url,
    chunk_number,
    content,
    metadata,
    1 - (crawled_pages.embedding <=> query_embedding) as similarity,
    version
  from crawled_pages
  where metadata @> filter
  order by crawled_pages.embedding <=> query_embedding
  limit match_count;
end;
$$;

-- Enhanced search function with similarity threshold and flexible filtering
create or replace function enhanced_match_crawled_pages (
  query_embedding vector(1536),
  match_count int default 10,
  similarity_threshold float default 0.3,
  filter jsonb DEFAULT '{}'::jsonb
) returns table (
  id bigint,
  url varchar,
  chunk_number integer,
  content text,
  metadata jsonb,
  similarity float,
  version integer
)
language plpgsql
as $$
#variable_conflict use_column
declare
  filter_condition text := '';
  key text;
  value text;
begin
  -- Build dynamic filter conditions for more flexible filtering
  if filter != '{}'::jsonb then
    for key, value in select * from jsonb_each_text(filter) loop
      if filter_condition != '' then
        filter_condition := filter_condition || ' AND ';
      end if;
      
      -- Handle different filter types
      if key = 'source' then
        filter_condition := filter_condition || format('metadata->>%L = %L', key, value);
      elsif key = 'path' then
        filter_condition := filter_condition || format('metadata->>%L = %L', key, value);
      elsif key = 'method' then
        filter_condition := filter_condition || format('metadata->>%L = %L', key, value);
      elsif key = 'section' then
        filter_condition := filter_condition || format('metadata->>%L = %L', key, value);
      else
        -- Default: exact match for other metadata fields
        filter_condition := filter_condition || format('metadata->>%L = %L', key, value);
      end if;
    end loop;
  end if;

  return query execute format('
    select
      cp.id,
      cp.url,
      cp.chunk_number,
      cp.content,
      cp.metadata,
      1 - (cp.embedding <=> $1) as similarity,
      cp.version
    from crawled_pages cp
    where (1 - (cp.embedding <=> $1)) >= $3
    %s
    order by cp.embedding <=> $1
    limit $2',
    case when filter_condition != '' then 'AND ' || filter_condition else '' end
  ) using query_embedding, match_count, similarity_threshold;
end;
$$;

-- Create a function to get the latest version of a document
create or replace function get_latest_version(p_url varchar)
returns integer
language plpgsql
as $$
declare
    latest_ver integer;
begin
    select coalesce(max(version)::integer, 0) into latest_ver
    from crawled_pages
    where url = p_url;
    
    return latest_ver;
end;
$$;

-- Create a function to compare document versions
create or replace function compare_document_versions(
  url varchar,
  old_version integer,
  new_version integer
) returns table (
  change_type varchar,
  change_summary text,
  change_impact varchar,  -- Changed from text to varchar to match table definition
  change_details jsonb
)
language plpgsql
as $$
begin
  return query
  with old_chunks as (
    select chunk_number, content, metadata
    from crawled_pages
    where crawled_pages.url = compare_document_versions.url
    and version = old_version
  ),
  new_chunks as (
    select chunk_number, content, metadata
    from crawled_pages
    where crawled_pages.url = compare_document_versions.url
    and version = new_version
  )
  select
    case
      when oc.chunk_number is null then 'added'::varchar
      when nc.chunk_number is null then 'deleted'::varchar
      else 'modified'::varchar
    end as change_type,
    case
      when oc.chunk_number is null then 'New content added'
      when nc.chunk_number is null then 'Content removed'
      else 'Content modified'
    end as change_summary,
    case
      when oc.chunk_number is null or nc.chunk_number is null then 'high'::varchar
      when oc.content != nc.content then 'medium'::varchar
      else 'low'::varchar
    end as change_impact,
    jsonb_build_object(
      'old_content', oc.content,
      'new_content', nc.content,
      'old_metadata', oc.metadata,
      'new_metadata', nc.metadata
    ) as change_details
  from old_chunks oc
  full outer join new_chunks nc on oc.chunk_number = nc.chunk_number
  where oc.chunk_number is null
     or nc.chunk_number is null
     or oc.content != nc.content;
end;
$$;

-- Enable RLS on the tables
alter table crawled_pages enable row level security;
alter table document_changes enable row level security;

-- Create policies that allow anyone to read
create policy "Allow public read access to crawled_pages"
  on crawled_pages
  for select
  to public
  using (true);

create policy "Allow public read access to document_changes"
  on document_changes
  for select
  to public
  using (true);

-- Table to track monitored documentations
create table if not exists monitored_documentations (
    id bigserial primary key,
    url varchar not null unique,
    date_added timestamp with time zone default timezone('utc'::text, now()) not null,
    crawl_type varchar not null,
    status varchar not null default 'active',
    metadata jsonb not null default '{}'::jsonb,
    last_crawled_at timestamp with time zone,
    notes text
);

-- Index for fast lookup by url
create index if not exists idx_monitored_documentations_url on monitored_documentations(url);

-- Enable RLS
alter table monitored_documentations enable row level security;

-- Allow public read access
create policy "Allow public read access to monitored_documentations"
  on monitored_documentations
  for select
  to public
  using (true);