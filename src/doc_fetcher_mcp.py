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
from urllib.parse import urlparse, urldefrag
from xml.etree import ElementTree
from dotenv import load_dotenv
from supabase import Client
from pathlib import Path
import requests
import asyncio
import json
import os
import re
from datetime import datetime

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode, MemoryAdaptiveDispatcher
from utils import (
    get_supabase_client, batch_upsert_documents, semantic_search_documents, is_openapi_url,
    fetch_openapi_spec, openapi_spec_to_markdown_chunks, is_sitemap, is_txt, parse_sitemap,
    smart_chunk_markdown, extract_section_info
)

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
# Helper Functions
# =========================
async def crawl_markdown_file(crawler: AsyncWebCrawler, url: str) -> list[dict[str, Any]]:
    """Crawl a .txt or markdown file and return a list of dicts with URL and markdown content."""
    crawl_config = CrawlerRunConfig()
    result = await crawler.arun(url=url, config=crawl_config)
    if result.success and result.markdown:
        return [{"url": url, "markdown": result.markdown}]
    print(f"Failed to crawl {url}: {result.error_message}")
    return []

def build_dispatcher(max_concurrent: int) -> MemoryAdaptiveDispatcher:
    return MemoryAdaptiveDispatcher(
        memory_threshold_percent=MEMORY_THRESHOLD_PERCENT,
        check_interval=CHECK_INTERVAL,
        max_session_permit=max_concurrent
    )

async def crawl_batch(crawler: AsyncWebCrawler, urls: list[str], max_concurrent: int = MAX_CONCURRENT) -> list[dict[str, Any]]:
    """Batch crawl multiple URLs in parallel."""
    print(f"[DEBUG] crawl_batch: Starting batch crawl for {len(urls)} URLs with max_concurrent={max_concurrent}")
    crawl_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, stream=False)
    dispatcher = build_dispatcher(max_concurrent)
    try:
        results = await crawler.arun_many(urls=urls, config=crawl_config, dispatcher=dispatcher)
        print(f"[DEBUG] crawl_batch: Finished batch crawl, got {len(results)} results")
        return [
            {"url": r.url, "markdown": r.markdown}
            for r in results if r.success and r.markdown
        ]
    except Exception as e:
        print(f"[ERROR] Exception in crawl_batch: {e}")
        return []

async def crawl_recursive_internal_links(
    crawler: AsyncWebCrawler, start_urls: list[str], max_depth: int = MAX_DEPTH, max_concurrent: int = MAX_CONCURRENT
) -> list[dict[str, Any]]:
    """Recursively crawl internal links from start URLs up to a maximum depth."""
    run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, stream=False)
    dispatcher = build_dispatcher(max_concurrent)
    visited = set()
    def normalize_url(url):
        return urldefrag(url)[0]
    current_urls = {normalize_url(u) for u in start_urls}
    results_all = []
    for _ in range(max_depth):
        urls_to_crawl = [normalize_url(url) for url in current_urls if normalize_url(url) not in visited]
        if not urls_to_crawl:
            break
        results = await crawler.arun_many(urls=urls_to_crawl, config=run_config, dispatcher=dispatcher)
        next_level_urls = set()
        for result in results:
            norm_url = normalize_url(result.url)
            visited.add(norm_url)
            if result.success and result.markdown:
                results_all.append({"url": result.url, "markdown": result.markdown})
                for link in result.links.get("internal", []):
                    next_url = normalize_url(link["href"])
                    if next_url not in visited:
                        next_level_urls.add(next_url)
        current_urls = next_level_urls
    return results_all

def build_metadata(chunk: str, i: int, url: str, crawl_type: str = None, version: int = 1) -> dict:
    meta = extract_section_info(chunk)
    meta.update({
        "chunk_index": i,
        "url": url,
        "source": urlparse(url).netloc,
        "version": version,
        "crawl_time": str(asyncio.current_task().get_coro().__name__)
    })
    if crawl_type:
        meta["crawl_type"] = crawl_type
    return meta

def analyze_change_impact(change: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze the impact of a change and provide recommendations.
    """
    analysis = {
        "severity": change.get("change_impact", "low"),
        "recommendations": [],
        "breaking_changes": False,
        "api_changes": False
    }
    old_content = change.get("change_details", {}).get("old_content", "") or ""
    new_content = change.get("change_details", {}).get("new_content", "") or ""
    api_patterns = [
        r"api\s+endpoint", r"api\s+version", r"request\s+parameters", r"response\s+format",
        r"http\s+method", r"authentication", r"headers", r"query\s+parameters"
    ]
    breaking_patterns = [
        r"breaking\s+change", r"deprecated", r"removed", r"no longer supported", r"changed from", r"replaced by"
    ]
    for pattern in api_patterns:
        if re.search(pattern, new_content, re.IGNORECASE):
            analysis["api_changes"] = True
            analysis["recommendations"].append(
                "API changes detected. Review API documentation and update client code if necessary."
            )
            break
    for pattern in breaking_patterns:
        if re.search(pattern, new_content, re.IGNORECASE):
            analysis["breaking_changes"] = True
            analysis["severity"] = "high"
            analysis["recommendations"].append(
                "Breaking changes detected. Immediate action required to update dependent systems."
            )
            break
    change_type = change.get("change_type", "unknown")
    if change_type == "added":
        analysis["recommendations"].append("New content added. Review for new features or functionality.")
    elif change_type == "deleted":
        analysis["recommendations"].append("Content removed. Check if removed functionality needs to be replaced.")
    elif change_type == "modified":
        analysis["recommendations"].append("Content modified. Review changes for impact on existing functionality.")
    return analysis

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
        result = supabase_client.rpc('get_latest_version', {'p_url': url}).execute()
        current_version = result.data if result.data is not None else 0
        run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, stream=False)
        result = await crawler.arun(url=url, config=run_config)
        if not result.success or not result.markdown:
            return json.dumps({"success": False, "url": url, "error": "Failed to crawl document"}, indent=2)
        chunks = smart_chunk_markdown(result.markdown)
        if current_version == 0:
            urls, chunk_numbers, contents, metadatas = [], [], [], []
            for i, chunk in enumerate(chunks):
                urls.append(url)
                chunk_numbers.append(i)
                contents.append(chunk)
                metadatas.append(build_metadata(chunk, i, url, version=1))
            url_to_full_document = {url: result.markdown}
            try:
                batch_upsert_documents(supabase_client, urls, chunk_numbers, contents, metadatas, url_to_full_document)
            except Exception as e:
                print(f"[ERROR] Exception in batch_upsert_documents: {e}")
                raise
            return json.dumps({"success": True, "url": url, "message": "First version of document stored", "version": 1}, indent=2)
        current_content = supabase_client.table("crawled_pages")\
            .select("content")\
            .eq("url", url)\
            .eq("version", current_version)\
            .order("chunk_number")\
            .execute()
        if not current_content.data:
            return json.dumps({"success": False, "url": url, "error": "Could not find current version content in database"}, indent=2)
        current_text = "\n".join(chunk["content"] for chunk in current_content.data if chunk.get("content"))
        if current_text == result.markdown:
            return json.dumps({"success": True, "url": url, "message": "No changes detected", "current_version": current_version, "changes_found": 0}, indent=2)
        new_version = current_version + 1
        urls, chunk_numbers, contents, metadatas = [], [], [], []
        for i, chunk in enumerate(chunks):
            urls.append(url)
            chunk_numbers.append(i)
            contents.append(chunk)
            metadatas.append(build_metadata(chunk, i, url, version=new_version))
        url_to_full_document = {url: result.markdown}
        try:
            batch_upsert_documents(supabase_client, urls, chunk_numbers, contents, metadatas, url_to_full_document)
        except Exception as e:
            print(f"[ERROR] Exception in batch_upsert_documents: {e}")
            raise
        try:
            comparison = supabase_client.rpc(
                'compare_document_versions',
                {'url': url, 'old_version': current_version, 'new_version': new_version}
            ).execute()
            changes = []
            if comparison and comparison.data:
                for change in comparison.data:
                    if not change:
                        continue
                    change_type = change.get("change_type", "unknown")
                    change_summary = change.get("change_summary", "No summary available")
                    change_impact = change.get("change_impact", "low")
                    change_details = change.get("change_details", {}) or {}
                    change_obj = {
                        "change_type": change_type,
                        "change_summary": change_summary,
                        "change_impact": change_impact,
                        "change_details": change_details
                    }
                    impact_analysis = analyze_change_impact(change_obj)
                    changes.append({
                        "type": change_type,
                        "summary": change_summary,
                        "impact": change_impact,
                        "details": change_details,
                        "analysis": impact_analysis
                    })
                if changes:
                    change_record = {
                        "url": url,
                        "version": new_version,
                        "change_type": "multiple" if len(changes) > 1 else changes[0]["type"],
                        "change_summary": f"Found {len(changes)} changes in version {new_version}",
                        "change_impact": max(c["impact"] for c in changes),
                        "change_details": {"changes": changes}
                    }
                    supabase_client.table("document_changes").upsert(change_record, on_conflict="url,version").execute()
            return json.dumps({
                "success": True,
                "url": url,
                "old_version": current_version,
                "new_version": new_version,
                "changes_found": len(changes),
                "changes": changes
            }, indent=2)
        except Exception as e:
            print(f"[ERROR] Exception in version comparison: {e}")
            return json.dumps({"success": False, "url": url, "error": f"Error comparing versions: {str(e)}"}, indent=2)
    except Exception as e:
        print(f"[ERROR] Exception in check_document_changes: {e}")
        return json.dumps({"success": False, "url": url, "error": str(e)}, indent=2)

@mcp.tool()
async def monitor_documentation(ctx: Context, url: str, notes: str = None) -> str:
    """
    Add a documentation URL for monitoring, crawl and index it, and store in monitored_documentations, crawled_pages, and document_changes.
    """
    try:
        supabase_client = ctx.request_context.lifespan_context.supabase_client
        existing = supabase_client.table("monitored_documentations").select("id, status").eq("url", url).execute()
        if existing.data and any(doc.get("status") == "active" for doc in existing.data):
            return json.dumps({"success": False, "url": url, "error": "Documentation already monitored"}, indent=2)
        crawl_type = "webpage"
        if is_openapi_url(url):
            crawl_type = "openapi"
        elif is_txt(url):
            crawl_type = "text_file"
        elif is_sitemap(url):
            crawl_type = "sitemap"
        insert_data = {
            "url": url,
            "crawl_type": crawl_type,
            "status": "active",
            "notes": notes or None,
            "date_added": datetime.utcnow().isoformat()
        }
        supabase_client.table("monitored_documentations").upsert(insert_data, on_conflict="url").execute()
        crawler = ctx.request_context.lifespan_context.crawler
        crawl_results = []
        chunk_count = 0
        if crawl_type == "openapi":
            spec = fetch_openapi_spec(url)
            if not spec:
                return json.dumps({"success": False, "url": url, "error": "Could not fetch or parse OpenAPI spec"}, indent=2)
            openapi_chunks = openapi_spec_to_markdown_chunks(spec, chunk_size=CHUNK_SIZE)
            urls = [url] * len(openapi_chunks)
            chunk_numbers = list(range(len(openapi_chunks)))
            contents = [c['content'] for c in openapi_chunks]
            metadatas = [dict(c['metadata'], url=url, source=urlparse(url).netloc, crawl_type='openapi', version=1) for c in openapi_chunks]
            url_to_full_document = {url: json.dumps(spec, indent=2)}
            batch_upsert_documents(supabase_client, urls, chunk_numbers, contents, metadatas, url_to_full_document, batch_size=20)
            change_record = {
                "url": url,
                "version": 1,
                "change_type": "added",
                "change_summary": "Initial version indexed",
                "change_impact": "high",
                "change_details": {"chunks": len(openapi_chunks)},
                "created_at": datetime.utcnow().isoformat()
            }
            supabase_client.table("document_changes").upsert(change_record, on_conflict="url,version").execute()
            supabase_client.table("monitored_documentations").update({"last_crawled_at": datetime.utcnow().isoformat()}).eq("url", url).execute()
            return json.dumps({"success": True, "url": url, "crawl_type": crawl_type, "chunks_stored": len(openapi_chunks), "message": "OpenAPI spec processed and stored"}, indent=2)
        elif crawl_type == "text_file":
            crawl_results = await crawl_markdown_file(crawler, url)
        elif crawl_type == "sitemap":
            sitemap_urls = parse_sitemap(url)
            if not sitemap_urls:
                return json.dumps({"success": False, "url": url, "error": "No URLs found in sitemap"}, indent=2)
            crawl_results = await crawl_batch(crawler, sitemap_urls, max_concurrent=MAX_CONCURRENT)
        else:
            crawl_results = await crawl_recursive_internal_links(crawler, [url], max_depth=MAX_DEPTH, max_concurrent=MAX_CONCURRENT)
        if not crawl_results:
            return json.dumps({"success": False, "url": url, "error": "No content found"}, indent=2)
        urls, chunk_numbers, contents, metadatas = [], [], [], []
        for doc in crawl_results:
            source_url = doc['url']
            md = doc['markdown']
            chunks = smart_chunk_markdown(md, chunk_size=CHUNK_SIZE)
            for i, chunk in enumerate(chunks):
                urls.append(source_url)
                chunk_numbers.append(i)
                contents.append(chunk)
                metadatas.append(build_metadata(chunk, i, source_url, crawl_type=crawl_type, version=1))
                chunk_count += 1
        url_to_full_document = {doc['url']: doc['markdown'] for doc in crawl_results}
        batch_upsert_documents(supabase_client, urls, chunk_numbers, contents, metadatas, url_to_full_document, batch_size=20)
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
        return json.dumps({"success": True, "url": url, "crawl_type": crawl_type, "pages_crawled": len(crawl_results), "chunks_stored": chunk_count, "message": "Documentation processed and stored"}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "url": url, "error": str(e)}, indent=2)

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

# --- Helper function for checking and updating document changes for a single URL ---
async def check_and_update_document_changes(ctx: Context, url: str) -> dict:
    """
    Check for changes in a document by comparing the latest version with the previous version.
    If changes are found, store the new version.
    Returns a dict with the result.
    """
    try:
        crawler = ctx.request_context.lifespan_context.crawler
        supabase_client = ctx.request_context.lifespan_context.supabase_client
        result = supabase_client.rpc('get_latest_version', {'p_url': url}).execute()
        current_version = result.data if result.data is not None else 0
        run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, stream=False)
        result = await crawler.arun(url=url, config=run_config)
        if not result.success or not result.markdown:
            return {"success": False, "url": url, "error": "Failed to crawl document"}
        chunks = smart_chunk_markdown(result.markdown)
        if current_version == 0:
            urls, chunk_numbers, contents, metadatas = [], [], [], []
            for i, chunk in enumerate(chunks):
                urls.append(url)
                chunk_numbers.append(i)
                contents.append(chunk)
                metadatas.append(build_metadata(chunk, i, url, version=1))
            url_to_full_document = {url: result.markdown}
            batch_upsert_documents(supabase_client, urls, chunk_numbers, contents, metadatas, url_to_full_document)
            return {"success": True, "url": url, "message": "First version of document stored", "version": 1}
        current_content = supabase_client.table("crawled_pages")\
            .select("content")\
            .eq("url", url)\
            .eq("version", current_version)\
            .order("chunk_number")\
            .execute()
        if not current_content.data:
            return {"success": False, "url": url, "error": "Could not find current version content in database"}
        current_text = "\n".join(chunk["content"] for chunk in current_content.data if chunk.get("content"))
        if current_text == result.markdown:
            return {"success": True, "url": url, "message": "No changes detected", "current_version": current_version, "changes_found": 0}
        new_version = current_version + 1
        urls, chunk_numbers, contents, metadatas = [], [], [], []
        for i, chunk in enumerate(chunks):
            urls.append(url)
            chunk_numbers.append(i)
            contents.append(chunk)
            metadatas.append(build_metadata(chunk, i, url, version=new_version))
        url_to_full_document = {url: result.markdown}
        batch_upsert_documents(supabase_client, urls, chunk_numbers, contents, metadatas, url_to_full_document)
        try:
            comparison = supabase_client.rpc(
                'compare_document_versions',
                {'url': url, 'old_version': current_version, 'new_version': new_version}
            ).execute()
            changes = []
            if comparison and comparison.data:
                for change in comparison.data:
                    if not change:
                        continue
                    change_type = change.get("change_type", "unknown")
                    change_summary = change.get("change_summary", "No summary available")
                    change_impact = change.get("change_impact", "low")
                    change_details = change.get("change_details", {}) or {}
                    change_obj = {
                        "change_type": change_type,
                        "change_summary": change_summary,
                        "change_impact": change_impact,
                        "change_details": change_details
                    }
                    impact_analysis = analyze_change_impact(change_obj)
                    changes.append({
                        "type": change_type,
                        "summary": change_summary,
                        "impact": change_impact,
                        "details": change_details,
                        "analysis": impact_analysis
                    })
                if changes:
                    change_record = {
                        "url": url,
                        "version": new_version,
                        "change_type": "multiple" if len(changes) > 1 else changes[0]["type"],
                        "change_summary": f"Found {len(changes)} changes in version {new_version}",
                        "change_impact": max(c["impact"] for c in changes),
                        "change_details": {"changes": changes}
                    }
                    supabase_client.table("document_changes").upsert(change_record, on_conflict="url,version").execute()
            return {"success": True, "url": url, "old_version": current_version, "new_version": new_version, "changes_found": len(changes), "changes": changes}
        except Exception as e:
            return {"success": False, "url": url, "error": f"Error comparing versions: {str(e)}"}
    except Exception as e:
        return {"success": False, "url": url, "error": str(e)}

@mcp.tool()
async def check_all_document_changes(ctx: Context) -> str:
    """
    Check for changes in all documents in the database.
    For each unique URL, crawl and check for changes, storing new versions if needed.
    Returns a summary of all results.
    """
    try:
        supabase_client = ctx.request_context.lifespan_context.supabase_client
        result = supabase_client.table("crawled_pages").select("url").execute()
        if not result.data:
            return json.dumps({"success": False, "error": "No URLs found in the database"}, indent=2)
        unique_urls = sorted(set(item["url"] for item in result.data if item.get("url")))
        all_results = []
        for url in unique_urls:
            res = await check_and_update_document_changes(ctx, url)
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