"""
DocMonitor MCP server for web crawling and RAG.

This server provides tools to crawl websites using Crawl4AI, automatically detecting
the appropriate crawl method based on URL type (sitemap, txt file, or regular webpage).
"""
from mcp.server.fastmcp import FastMCP, Context
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from supabase import Client
from pathlib import Path
import asyncio
import json
import os
import logging
from datetime import datetime

from crawl4ai import AsyncWebCrawler, BrowserConfig
from utils import (
    get_supabase_client, batch_upsert_documents, semantic_search_documents, is_openapi_url,
    fetch_openapi_spec, openapi_spec_to_markdown_chunks, is_sitemap, is_txt, parse_sitemap,
    smart_chunk_markdown, extract_section_info, improved_semantic_search, semantic_chunk_markdown,
    crawl_markdown_file, build_dispatcher, crawl_batch, crawl_website_recursively,
    build_metadata, analyze_change_impact, check_and_update_document_changes,
    process_openapi_documentation, process_sitemap_documentation, 
    process_text_file_documentation, process_website_documentation
)

# Import our new ingestion components
from ingestion import DocumentRouter, AdaptiveChunker

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# =========================
# Constants & Config
# =========================
CHUNK_SIZE = 5000
MAX_CONCURRENT = 10
MAX_DEPTH = 3
MEMORY_THRESHOLD_PERCENT = 70.0
CHECK_INTERVAL = 1.0

# Load environment variables from the project root .env file
project_root = Path(__file__).resolve().parent.parent
dotenv_path = project_root / '.env'
load_dotenv(dotenv_path, override=True)

# =========================
# Context
# =========================
@dataclass
class DocFetcherContext:
    """Context for the DocMonitor MCP server."""
    crawler: AsyncWebCrawler
    supabase_client: Client

@asynccontextmanager
async def docfetcher_lifespan(server: FastMCP) -> AsyncIterator[DocFetcherContext]:
    """
    Manages the DocMonitor client lifecycle.
    """
    browser_config = BrowserConfig(headless=True, verbose=False)
    crawler = AsyncWebCrawler(config=browser_config)
    await crawler.__aenter__()
    supabase_client = get_supabase_client()
    try:
        yield DocFetcherContext(crawler=crawler, supabase_client=supabase_client)
    finally:
        await crawler.__aexit__(None, None, None)

# =========================
# FastMCP Server Init
# =========================
mcp = FastMCP(
    "doc-monitor",
    description="MCP server for RAG and web crawling with DocMonitor",
    lifespan=docfetcher_lifespan,
    host=os.getenv("HOST", "0.0.0.0"),
    port=os.getenv("PORT", "8051")
)

# =========================
# MCP-Specific Configuration
# =========================

# =========================
# MCP Tool Functions
# =========================
@mcp.tool()
async def check_document_changes(ctx: Context, url: str) -> str:
    """
    Check for changes in a document by comparing the latest version with the previous version.
    """
    try:
        crawler = ctx.request_context.lifespan_context.crawler
        supabase_client = ctx.request_context.lifespan_context.supabase_client
        result = await check_and_update_document_changes(crawler, supabase_client, url)
        return json.dumps(result, indent=2)
    except Exception as e:
        print(f"[ERROR] Exception in check_document_changes: {e}")
        return json.dumps({"success": False, "url": url, "error": str(e)}, indent=2)

@mcp.tool()
async def monitor_documentation(ctx: Context, url: str, notes: str = None) -> str:
    """
    Add a documentation URL for monitoring, crawl and index it, and store in monitored_documentations, crawled_pages, and document_changes.
    """
    logger.info(f"🚀 Starting documentation monitoring for: {url}")
    
    try:
        supabase_client = ctx.request_context.lifespan_context.supabase_client
        crawler = ctx.request_context.lifespan_context.crawler
        
        logger.info("✅ Retrieved crawler and supabase client from context")
        
        # Check if already monitored
        logger.info(f"🔍 Checking if {url} is already monitored...")
        existing = supabase_client.table("monitored_documentations").select("id, status").eq("url", url).execute()
        if existing.data and any(doc.get("status") == "active" for doc in existing.data):
            logger.warning(f"⚠️ Documentation already monitored: {url}")
            return json.dumps({"success": False, "url": url, "error": "Documentation already monitored"}, indent=2)
        
        # Determine crawl type using our new DocumentRouter
        logger.info(f"🔍 Detecting document type for: {url}")
        router = DocumentRouter()
        doc_type = router.detect_document_type(url)
        
        # Map document type to crawl type for legacy compatibility
        crawl_type_mapping = {
            "openapi": "openapi",
            "swagger": "openapi", 
            "llms_txt": "text_file",
            "markdown": "text_file",
            "text": "text_file",
            "sitemap": "sitemap",
            "webpage": "webpage"
        }
        crawl_type = crawl_type_mapping.get(doc_type.value, "webpage")
        logger.info(f"✅ Detected document type: {doc_type.value} -> crawl_type: {crawl_type}")
        
        # Insert monitoring record
        logger.info(f"💾 Inserting monitoring record for {url}")
        insert_data = {
            "url": url,
            "crawl_type": crawl_type,
            "status": "active",
            "notes": notes or None,
            "date_added": datetime.utcnow().isoformat()
        }
        supabase_client.table("monitored_documentations").upsert(insert_data, on_conflict="url").execute()
        logger.info("✅ Monitoring record inserted successfully")
        
        # Process documentation based on type
        logger.info(f"🔄 Processing documentation with type: {crawl_type}")
        try:
            if crawl_type == "openapi":
                logger.info("🔧 Processing OpenAPI documentation...")
                crawl_results, chunk_count = await process_openapi_documentation(supabase_client, url, CHUNK_SIZE)
                message = "OpenAPI spec processed and stored"
            elif crawl_type == "text_file":
                logger.info("📄 Processing text file documentation...")
                crawl_results = await process_text_file_documentation(crawler, url)
                chunk_count = await _process_crawl_results(supabase_client, crawl_results, crawl_type)
                message = "Text file processed and stored"
            elif crawl_type == "sitemap":
                logger.info("🗺️ Processing sitemap documentation...")
                crawl_results = await process_sitemap_documentation(crawler, url, MAX_CONCURRENT)
                chunk_count = await _process_crawl_results(supabase_client, crawl_results, crawl_type)
                message = "Sitemap processed and stored"
            else:
                logger.info("🌐 Processing website documentation...")
                crawl_results = await process_website_documentation(crawler, url, MAX_DEPTH, 100, 0.5)
                chunk_count = await _process_crawl_results(supabase_client, crawl_results, crawl_type)
                message = "Website processed and stored"
            
            if not crawl_results:
                logger.error(f"❌ No content found for {url}")
                return json.dumps({"success": False, "url": url, "error": "No content found"}, indent=2)
            
            logger.info(f"✅ Processing completed: {len(crawl_results)} pages, {chunk_count} chunks")
            
            # Record initial change
            logger.info("📝 Recording initial change record...")
            change_record = {
                "url": url,
                "version": 1,
                "change_type": "added",
                "change_summary": "Initial version indexed",
                "change_impact": "high",
                "change_details": {"chunks": chunk_count},
                "created_at": datetime.utcnow().isoformat()
            }
            supabase_client.table("document_changes").upsert(change_record, on_conflict="url,version").execute()
            supabase_client.table("monitored_documentations").update({"last_crawled_at": datetime.utcnow().isoformat()}).eq("url", url).execute()
            logger.info("✅ Change record and monitoring update completed")
            
            result = {
                "success": True, 
                "url": url, 
                "crawl_type": crawl_type, 
                "document_type": doc_type.value,
                "pages_crawled": len(crawl_results), 
                "chunks_stored": chunk_count, 
                "message": message
            }
            logger.info(f"🎉 Documentation monitoring completed successfully: {result}")
            return json.dumps(result, indent=2)
            
        except ValueError as e:
            logger.error(f"❌ ValueError during processing: {str(e)}")
            return json.dumps({"success": False, "url": url, "error": str(e)}, indent=2)
            
    except Exception as e:
        logger.error(f"❌ Unexpected error in monitor_documentation: {str(e)}")
        return json.dumps({"success": False, "url": url, "error": str(e)}, indent=2)

async def _process_crawl_results(supabase_client, crawl_results: list, crawl_type: str) -> int:
    """Helper function to process crawl results and return chunk count."""
    logger.info(f"🚀 Processing {len(crawl_results)} crawl results with crawl_type: {crawl_type}")
    
    # Initialize our new adaptive chunker
    chunker = AdaptiveChunker()
    logger.info("✅ AdaptiveChunker initialized")
    
    urls, chunk_numbers, contents, metadatas = [], [], [], []
    chunk_count = 0
    
    for doc_idx, doc in enumerate(crawl_results):
        source_url = doc['url']
        
        # Handle different data formats from our new workflow functions
        if 'markdown_chunks' in doc:
            # New format from our updated workflow functions
            chunks = doc['markdown_chunks']
            original_markdown = doc.get('original_markdown', '')
            logger.info(f"📄 Doc {doc_idx+1}: Using pre-chunked content - {len(chunks)} chunks")
        else:
            # Legacy format - need to chunk it
            md = doc.get('markdown', '')
            if not md:
                logger.warning(f"⚠️ Doc {doc_idx+1}: No markdown content found, skipping")
                continue
                
            logger.info(f"📄 Doc {doc_idx+1}: Chunking {len(md)} characters with AdaptiveChunker")
            chunks = chunker.semantic_chunk(md)
            original_markdown = md
            logger.info(f"✅ Doc {doc_idx+1}: Created {len(chunks)} semantic chunks")
        
        # Process each chunk
        for i, chunk in enumerate(chunks):
            if not chunk or len(chunk.strip()) < 50:  # Skip very small chunks
                logger.warning(f"⚠️ Skipping very small chunk {i} ({len(chunk)} chars)")
                continue
                
            urls.append(source_url)
            chunk_numbers.append(i)
            contents.append(chunk)
            metadata = build_metadata(chunk, i, source_url, crawl_type=crawl_type, version=1)
            metadatas.append(metadata)
            chunk_count += 1
            
            if i == 0:  # Log first chunk details
                logger.info(f"📝 First chunk preview: {chunk[:100]}...")
    
    logger.info(f"📊 Total chunks to store: {chunk_count}")
    
    if chunk_count == 0:
        logger.error("❌ No valid chunks to store!")
        return 0
    
    # Prepare url_to_full_document mapping
    url_to_full_document = {}
    for doc in crawl_results:
        url = doc['url']
        if 'original_markdown' in doc:
            url_to_full_document[url] = doc['original_markdown']
        else:
            url_to_full_document[url] = doc.get('markdown', '')
    
    logger.info(f"💾 Storing {chunk_count} chunks in database...")
    
    try:
        batch_upsert_documents(supabase_client, urls, chunk_numbers, contents, metadatas, url_to_full_document, batch_size=20)
        logger.info(f"✅ Successfully stored {chunk_count} chunks in database")
    except Exception as e:
        logger.error(f"❌ Failed to store chunks in database: {str(e)}")
        raise
    
    return chunk_count

@mcp.tool()
async def get_available_sources(ctx: Context) -> str:
    """
    Get all available sources based on unique source metadata values.
    """
    try:
        supabase_client = ctx.request_context.lifespan_context.supabase_client
        result = supabase_client.from_('crawled_pages')\
            .select('metadata')\
            .not_.is_('metadata->>source', 'null')\
            .execute()
        unique_sources = set()
        if result.data:
            for item in result.data:
                source = item.get('metadata', {}).get('source')
                if source:
                    unique_sources.add(source)
        sources = sorted(list(unique_sources))
        return json.dumps({"success": True, "sources": sources, "count": len(sources)}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)



@mcp.tool()
async def check_all_document_changes(ctx: Context) -> str:
    """
    Check for changes in all documents in the database.
    For each unique URL, crawl and check for changes, storing new versions if needed.
    Returns a summary of all results.
    """
    try:
        crawler = ctx.request_context.lifespan_context.crawler
        supabase_client = ctx.request_context.lifespan_context.supabase_client
        
        # Get all unique URLs
        result = supabase_client.table("crawled_pages").select("url").execute()
        if not result.data:
            return json.dumps({"success": False, "error": "No URLs found in the database"}, indent=2)
        
        unique_urls = sorted(set(item["url"] for item in result.data if item.get("url")))
        all_results = []
        
        # Check each URL for changes
        for url in unique_urls:
            res = await check_and_update_document_changes(crawler, supabase_client, url)
            all_results.append(res)
        
        summary = {"success": True, "total_urls_checked": len(unique_urls), "results": all_results}
        return json.dumps(summary, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@mcp.tool()
async def perform_rag_query(ctx: Context, query: str, source: str = None, match_count: int = 5, endpoint: str = None, method: str = None) -> str:
    """
    Perform a RAG (Retrieval Augmented Generation) query on the stored content.
    Uses vector search and supports filtering by source, endpoint, and method.
    """
    try:
        supabase_client = ctx.request_context.lifespan_context.supabase_client
        filter_metadata = {}
        if source:
            filter_metadata["source"] = source
        if endpoint:
            filter_metadata["path"] = endpoint
        if method:
            filter_metadata["method"] = method.upper()
        docs = semantic_search_documents(supabase_client, query, match_count, filter_metadata if filter_metadata else None)
        return json.dumps({"success": True, "query": query, "filter": filter_metadata, "context_documents": docs, "count": len(docs)}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "query": query, "error": str(e)}, indent=2)

@mcp.tool()
async def advanced_rag_query(ctx: Context, query: str, source: str = None, match_count: int = 5, endpoint: str = None, method: str = None, similarity_threshold: float = 0.3, enable_reranking: bool = True) -> str:
    """
    Perform an advanced RAG query with improved semantic search, hybrid retrieval, and reranking.
    
    Args:
        query: The search query
        source: Filter by source domain (optional)
        match_count: Number of results to return (default: 5)
        endpoint: Filter by API endpoint path (optional)
        method: Filter by HTTP method (optional)
        similarity_threshold: Minimum similarity score (0-1, default: 0.3)
        enable_reranking: Whether to enable result reranking (default: True)
    
    Returns:
        JSON with improved search results and metadata
    """
    try:
        supabase_client = ctx.request_context.lifespan_context.supabase_client
        
        # Build filter metadata
        filter_metadata = {}
        if source:
            filter_metadata["source"] = source
        if endpoint:
            filter_metadata["path"] = endpoint
        if method:
            filter_metadata["method"] = method.upper()
        
        # Use improved semantic search
        docs = improved_semantic_search(
            supabase_client, 
            query, 
            match_count=match_count,
            filter_metadata=filter_metadata if filter_metadata else None,
            similarity_threshold=similarity_threshold,
            enable_reranking=enable_reranking
        )
        
        # Add query analysis
        query_analysis = {
            "original_query": query,
            "filter_applied": filter_metadata,
            "similarity_threshold": similarity_threshold,
            "reranking_enabled": enable_reranking,
            "results_found": len(docs)
        }
        
        # Enhance results with additional metadata
        enhanced_docs = []
        for doc in docs:
            enhanced_doc = dict(doc)
            
            # Add relevance indicators
            content = doc.get('content', '').lower()
            query_terms = set(query.lower().split())
            
            enhanced_doc['relevance_indicators'] = {
                'similarity_score': doc.get('similarity', 0),
                'rerank_score': doc.get('rerank_score'),
                'exact_matches': sum(1 for term in query_terms if term in content),
                'content_length': len(doc.get('content', '')),
                'chunk_number': doc.get('chunk_number', 0)
            }
            
            enhanced_docs.append(enhanced_doc)
        
        return json.dumps({
            "success": True,
            "query_analysis": query_analysis,
            "context_documents": enhanced_docs,
            "count": len(enhanced_docs),
            "search_method": "advanced_semantic_search_with_reranking"
        }, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "query": query, "error": str(e)}, indent=2)

@mcp.tool()
async def get_document_history(ctx: Context, url: str) -> str:
    """
    Get the change history for a document.
    """
    try:
        supabase_client = ctx.request_context.lifespan_context.supabase_client
        result = supabase_client.table("document_changes")\
            .select("*")\
            .eq("url", url)\
            .order("version", desc=True)\
            .execute()
        return json.dumps({"success": True, "url": url, "history": result.data}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "url": url, "error": str(e)}, indent=2)

@mcp.tool()
async def list_monitored_documentations(ctx: Context) -> str:
    """
    List all documentation URLs currently being monitored.
    """
    try:
        supabase_client = ctx.request_context.lifespan_context.supabase_client
        result = supabase_client.table("monitored_documentations").select("url, date_added, crawl_type, status, last_crawled_at, notes, metadata").eq("status", "active").order("date_added").execute()
        return json.dumps({"success": True, "monitored_documentations": result.data or []}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@mcp.tool()
async def delete_documentation_from_monitoring(ctx: Context, url: str) -> str:
    """
    Delete a documentation URL from monitoring (set status to 'deleted').
    """
    try:
        supabase_client = ctx.request_context.lifespan_context.supabase_client
        existing = supabase_client.table("monitored_documentations").select("id, status").eq("url", url).execute()
        if not existing.data:
            return json.dumps({"success": False, "url": url, "error": "Documentation not found"}, indent=2)
        supabase_client.table("monitored_documentations").update({"status": "deleted"}).eq("url", url).execute()
        return json.dumps({"success": True, "url": url, "message": "Documentation removed from monitoring"}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "url": url, "error": str(e)}, indent=2)

# =========================
# Entrypoint
# =========================
async def main():
    transport = os.getenv("TRANSPORT", "sse")
    if transport == 'sse':
        await mcp.run_sse_async()
    else:
        await mcp.run_stdio_async()

if __name__ == "__main__":
    asyncio.run(main())