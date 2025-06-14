"""
High-level document workflows for the doc-monitor MCP server.
Handles document processing workflows, change detection, and workflow orchestration.
"""
import json
from datetime import datetime
from typing import List, Dict, Any, Tuple
from crawl4ai import CrawlerRunConfig, CacheMode

from openapi import fetch_openapi_spec, openapi_spec_to_markdown_chunks
from url_utils import parse_sitemap
from crawling import crawl_markdown_file, crawl_batch, crawl_website_recursively
from processing import semantic_chunk_markdown, build_metadata, analyze_change_impact
from database import batch_upsert_documents
from ingestion import DocumentRouter, AdaptiveChunker


async def process_openapi_documentation(supabase_client, url: str, chunk_size: int = 5000) -> Tuple[List[Dict[str, Any]], int]:
    """
    Process OpenAPI specification and return crawl results and chunk count.
    
    Args:
        supabase_client: Supabase client instance
        url: URL of the OpenAPI specification
        chunk_size: Maximum chunk size
        
    Returns:
        Tuple containing (crawl_results, chunk_count)
    """
    spec = fetch_openapi_spec(url)
    if not spec:
        raise ValueError("Could not fetch or parse OpenAPI spec")
    
    # Convert spec to markdown chunks
    openapi_chunks = openapi_spec_to_markdown_chunks(spec, chunk_size=chunk_size)
    
    # Prepare data for batch upsert
    urls = [url] * len(openapi_chunks)
    chunk_numbers = list(range(len(openapi_chunks)))
    contents = [chunk['content'] for chunk in openapi_chunks]
    metadatas = [
        dict(chunk['metadata'], url=url, source=url.split('/')[2], crawl_type='openapi', version=1)
        for chunk in openapi_chunks
    ]
    url_to_full_document = {url: json.dumps(spec, indent=2)}
    
    # Store in database
    batch_upsert_documents(
        supabase_client, urls, chunk_numbers, contents, metadatas, 
        url_to_full_document, batch_size=20
    )
    
    return [{"url": url, "markdown": json.dumps(spec, indent=2)}], len(openapi_chunks)


async def process_sitemap_documentation(crawler, url: str, max_concurrent: int = 10) -> List[Dict[str, Any]]:
    """
    Process sitemap and return crawl results with semantic chunks.
    
    Args:
        crawler: AsyncWebCrawler instance
        url: URL of the sitemap
        max_concurrent: Maximum concurrent connections
        
    Returns:
        List of crawl results with semantically chunked markdown.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"🗺️ Processing sitemap: {url} (max_concurrent={max_concurrent})")
    
    sitemap_urls = parse_sitemap(url)
    if not sitemap_urls:
        logger.error(f"❌ No URLs found in sitemap: {url}")
        raise ValueError("No URLs found in sitemap")
    
    logger.info(f"✅ Found {len(sitemap_urls)} URLs in sitemap")
    
    # Crawl all URLs from sitemap
    logger.info(f"🕷️ Crawling {len(sitemap_urls)} URLs from sitemap...")
    crawl_results = await crawl_batch(crawler, sitemap_urls, max_concurrent=max_concurrent)
    
    if not crawl_results:
        logger.error(f"❌ No content retrieved from sitemap URLs")
        return []
    
    logger.info(f"✅ Sitemap crawling completed: {len(crawl_results)} pages retrieved")
    
    # Initialize our chunking system
    chunker = AdaptiveChunker()
    router = DocumentRouter()
    logger.info("✅ Initialized AdaptiveChunker and DocumentRouter")
    
    processed_results = []
    
    for idx, result in enumerate(crawl_results):
        raw_text = result.get("markdown", "")
        if not raw_text:
            logger.warning(f"⚠️ Sitemap page {idx+1}: No markdown content found")
            continue
        
        page_url = result.get("url", "")
        logger.info(f"📄 Sitemap page {idx+1}/{len(crawl_results)}: Processing {len(raw_text)} characters from {page_url}")
        
        # Detect document type for this specific page
        doc_type = router.detect_document_type(page_url)
        
        # Use adaptive chunking
        logger.info(f"🧩 Chunking sitemap page {idx+1} with AdaptiveChunker...")
        chunks = chunker.semantic_chunk(raw_text)
        logger.info(f"✅ Created {len(chunks)} semantic chunks for sitemap page {idx+1}")
        
        # Return in the format expected by _process_crawl_results
        processed_results.append({
            "url": page_url,
            "markdown": raw_text,  # Keep original for compatibility
            "markdown_chunks": chunks,  # Our new chunked content
            "original_markdown": raw_text,  # Explicit original content
            "document_type": doc_type.value,
            "original_word_count": len(raw_text.split()),
            "chunk_count": len(chunks)
        })
        
        logger.info(f"📋 Sitemap page {idx+1} summary: {len(chunks)} chunks, {len(raw_text.split())} words")
    
    logger.info(f"✅ Processed {len(processed_results)} sitemap pages successfully")
    return processed_results


async def process_text_file_documentation(crawler, url: str) -> List[Dict[str, Any]]:
    """
    Process text file and return crawl results with semantic chunks.
    
    Args:
        crawler: AsyncWebCrawler instance
        url: URL of the text file
        
    Returns:
        List of crawl results with semantically chunked markdown.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"🔄 Processing text file: {url}")
    
    # 1. Instantiate our new ingestion components
    router = DocumentRouter()
    chunker = AdaptiveChunker()
    logger.info("✅ Initialized DocumentRouter and AdaptiveChunker")

    # 2. Crawl the file to get the raw content
    logger.info(f"🕷️ Crawling text file: {url}")
    crawl_results = await crawl_markdown_file(crawler, url)
    if not crawl_results:
        logger.error(f"❌ No content retrieved from {url}")
        return []

    logger.info(f"✅ Retrieved {len(crawl_results)} documents from crawling")

    # 3. Process each crawled document
    processed_results = []
    for idx, result in enumerate(crawl_results):
        raw_text = result.get("markdown", "")
        if not raw_text:
            logger.warning(f"⚠️ Document {idx+1}: No markdown content found")
            continue
            
        logger.info(f"📄 Document {idx+1}: Processing {len(raw_text)} characters")
            
        # 4. Use the router to detect the document type
        doc_type = router.detect_document_type(url)
        logger.info(f"🔍 Detected document type: {doc_type}")

        # 5. Use the chunker to split the content into semantic chunks
        logger.info(f"🧩 Chunking document {idx+1} with AdaptiveChunker...")
        chunks = chunker.semantic_chunk(raw_text)
        logger.info(f"✅ Created {len(chunks)} semantic chunks for document {idx+1}")
        
        # Return in the format expected by _process_crawl_results
        processed_results.append({
            "url": result["url"],
            "markdown": raw_text,  # Keep original for compatibility
            "markdown_chunks": chunks,  # Our new chunked content
            "original_markdown": raw_text,  # Explicit original content
            "document_type": doc_type.value,
            "original_word_count": len(raw_text.split()),
            "chunk_count": len(chunks)
        })
        
        logger.info(f"📋 Document {idx+1} summary: {len(chunks)} chunks, {len(raw_text.split())} words")

    logger.info(f"✅ Processed {len(processed_results)} documents successfully")
    return processed_results


async def process_website_documentation(
    crawler, 
    url: str, 
    max_depth: int = 3, 
    max_pages: int = 100, 
    delay: float = 0.5
) -> List[Dict[str, Any]]:
    """
    Process website recursively and return crawl results with semantic chunks.
    
    Args:
        crawler: AsyncWebCrawler instance
        url: Starting URL for crawling
        max_depth: Maximum crawl depth
        max_pages: Maximum number of pages to crawl
        delay: Delay between requests
        
    Returns:
        List of crawl results with semantically chunked markdown.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"🌐 Processing website: {url} (max_depth={max_depth}, max_pages={max_pages})")
    
    crawl_results = await crawl_website_recursively(
        crawler, url, max_depth=max_depth, max_pages=max_pages, delay=delay
    )
    
    if not crawl_results:
        logger.error(f"❌ No content retrieved from website crawling: {url}")
        return []
    
    logger.info(f"✅ Website crawling completed: {len(crawl_results)} pages retrieved")
    
    chunker = AdaptiveChunker()
    router = DocumentRouter()
    logger.info("✅ Initialized AdaptiveChunker and DocumentRouter")
    
    processed_results = []

    for idx, result in enumerate(crawl_results):
        raw_text = result.get("markdown", "")
        if not raw_text:
            logger.warning(f"⚠️ Page {idx+1}: No markdown content found")
            continue
        
        page_url = result.get("url", url)
        logger.info(f"📄 Page {idx+1}/{len(crawl_results)}: Processing {len(raw_text)} characters from {page_url}")
        
        # Detect document type for this specific page
        doc_type = router.detect_document_type(page_url)
        
        # Use adaptive chunking
        logger.info(f"🧩 Chunking page {idx+1} with AdaptiveChunker...")
        chunks = chunker.semantic_chunk(raw_text)
        logger.info(f"✅ Created {len(chunks)} semantic chunks for page {idx+1}")
        
        # Return in the format expected by _process_crawl_results
        processed_results.append({
            "url": page_url,
            "markdown": raw_text,  # Keep original for compatibility
            "markdown_chunks": chunks,  # Our new chunked content
            "original_markdown": raw_text,  # Explicit original content
            "title": result.get("title", ""),
            "depth": result.get("depth", 0),
            "document_type": doc_type.value,
            "original_word_count": len(raw_text.split()),
            "chunk_count": len(chunks)
        })
        
        logger.info(f"📋 Page {idx+1} summary: {len(chunks)} chunks, {len(raw_text.split())} words, depth={result.get('depth', 0)}")
        
    logger.info(f"✅ Processed {len(processed_results)} pages successfully")
    return processed_results


async def check_and_update_document_changes(crawler, supabase_client, url: str) -> Dict[str, Any]:
    """
    Check for changes in a document by comparing the latest version with the previous version.
    If changes are found, store the new version.
    
    Args:
        crawler: AsyncWebCrawler instance
        supabase_client: Supabase client instance
        url: URL to check for changes
        
    Returns:
        Dictionary with the result of the change check
    """
    try:
        # Get current version from database
        result = supabase_client.rpc('get_latest_version', {'p_url': url}).execute()
        current_version = result.data if result.data is not None else 0
        
        # Crawl the current content
        run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, stream=False)
        result = await crawler.arun(url=url, config=run_config)
        
        if not result.success or not result.markdown:
            return {"success": False, "url": url, "error": "Failed to crawl document"}
        
        chunker = AdaptiveChunker()
        chunks = chunker.semantic_chunk(result.markdown)
        
        # If this is the first version, store it
        if current_version == 0:
            return await _store_initial_version(supabase_client, url, result.markdown, chunks)
        
        # Compare with existing content
        current_content = supabase_client.table("crawled_pages")\
            .select("content")\
            .eq("url", url)\
            .eq("version", current_version)\
            .order("chunk_number")\
            .execute()
        
        if not current_content.data:
            return {"success": False, "url": url, "error": "Could not find current version content in database"}
        
        current_text = "\n".join(chunk["content"] for chunk in current_content.data if chunk.get("content"))
        
        # Check if content has changed
        if current_text == result.markdown:
            return {
                "success": True, 
                "url": url, 
                "message": "No changes detected", 
                "current_version": current_version, 
                "changes_found": 0
            }
        
        # Store new version and detect changes
        return await _store_new_version_and_detect_changes(
            supabase_client, url, result.markdown, chunks, current_version
        )
        
    except Exception as e:
        return {"success": False, "url": url, "error": str(e)}


async def _store_initial_version(supabase_client, url: str, markdown: str, chunks: List[str]) -> Dict[str, Any]:
    """Store the initial version of a document."""
    urls, chunk_numbers, contents, metadatas = [], [], [], []
    
    for i, chunk in enumerate(chunks):
        urls.append(url)
        chunk_numbers.append(i)
        contents.append(chunk)
        metadatas.append(build_metadata(chunk, i, url, version=1))
    
    url_to_full_document = {url: markdown}
    batch_upsert_documents(supabase_client, urls, chunk_numbers, contents, metadatas, url_to_full_document)
    
    return {
        "success": True, 
        "url": url, 
        "message": "First version of document stored", 
        "version": 1
    }


async def _store_new_version_and_detect_changes(
    supabase_client, 
    url: str, 
    markdown: str, 
    chunks: List[str], 
    current_version: int
) -> Dict[str, Any]:
    """Store new version and detect changes."""
    new_version = current_version + 1
    urls, chunk_numbers, contents, metadatas = [], [], [], []
    
    for i, chunk in enumerate(chunks):
        urls.append(url)
        chunk_numbers.append(i)
        contents.append(chunk)
        metadatas.append(build_metadata(chunk, i, url, version=new_version))
    
    url_to_full_document = {url: markdown}
    batch_upsert_documents(supabase_client, urls, chunk_numbers, contents, metadatas, url_to_full_document)
    
    # Compare versions and detect changes
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
                
                # Analyze impact
                impact_analysis = analyze_change_impact(change_obj)
                changes.append({
                    "type": change_type,
                    "summary": change_summary,
                    "impact": change_impact,
                    "details": change_details,
                    "analysis": impact_analysis
                })
            
            # Store change record if changes found
            if changes:
                change_record = {
                    "url": url,
                    "version": new_version,
                    "change_type": "multiple" if len(changes) > 1 else changes[0]["type"],
                    "change_summary": f"Found {len(changes)} changes in version {new_version}",
                    "change_impact": max(c["impact"] for c in changes) if changes else "low",
                    "change_details": {"changes": changes},
                    "created_at": datetime.utcnow().isoformat()
                }
                supabase_client.table("document_changes").upsert(
                    change_record, on_conflict="url,version"
                ).execute()
        
        return {
            "success": True, 
            "url": url, 
            "old_version": current_version, 
            "new_version": new_version, 
            "changes_found": len(changes), 
            "changes": changes
        }
        
    except Exception as e:
        return {
            "success": False, 
            "url": url, 
            "error": f"Error comparing versions: {str(e)}"
        }


def create_crawl_summary(crawl_results: List[Dict[str, Any]], crawl_type: str) -> Dict[str, Any]:
    """
    Create a summary of crawl results.
    
    Args:
        crawl_results: List of crawl results
        crawl_type: Type of crawl operation
        
    Returns:
        Summary dictionary
    """
    total_pages = len(crawl_results)
    total_content_length = sum(len(doc.get('markdown', '')) for doc in crawl_results)
    average_content_length = total_content_length // total_pages if total_pages > 0 else 0
    
    urls = [doc.get('url', '') for doc in crawl_results]
    unique_domains = len(set(url.split('/')[2] if len(url.split('/')) > 2 else url for url in urls))
    
    return {
        "crawl_type": crawl_type,
        "total_pages": total_pages,
        "total_content_length": total_content_length,
        "average_content_length": average_content_length,
        "unique_domains": unique_domains,
        "urls": urls[:10],  # First 10 URLs for reference
        "timestamp": datetime.utcnow().isoformat()
    } 