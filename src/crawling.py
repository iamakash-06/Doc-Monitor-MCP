"""
Web crawling operations for the doc-monitor MCP server.
Handles various types of web crawling including batch, recursive, and file crawling.
"""
import asyncio
from typing import List, Dict, Any
from urllib.parse import urljoin, urldefrag, urlparse
import html2text


async def crawl_markdown_file(crawler, url: str) -> List[Dict[str, Any]]:
    """
    Crawl a .txt or markdown file and return a list of dicts with URL and markdown content.
    """
    from crawl4ai import CrawlerRunConfig
    
    crawl_config = CrawlerRunConfig()
    result = await crawler.arun(url=url, config=crawl_config)
    
    if result.success and result.markdown:
        return [{"url": url, "markdown": result.markdown}]
    
    print(f"Failed to crawl {url}: {result.error_message}")
    return []


def build_dispatcher(max_concurrent: int, memory_threshold_percent: float = 70.0, check_interval: float = 1.0):
    """
    Build a memory adaptive dispatcher for crawling operations.
    
    Args:
        max_concurrent: Maximum number of concurrent sessions
        memory_threshold_percent: Memory threshold percentage
        check_interval: Check interval in seconds
        
    Returns:
        MemoryAdaptiveDispatcher instance
    """
    from crawl4ai import MemoryAdaptiveDispatcher
    
    return MemoryAdaptiveDispatcher(
        memory_threshold_percent=memory_threshold_percent,
        check_interval=check_interval,
        max_session_permit=max_concurrent
    )


async def crawl_batch(
    crawler, 
    urls: List[str], 
    max_concurrent: int = 10, 
    memory_threshold_percent: float = 70.0, 
    check_interval: float = 1.0
) -> List[Dict[str, Any]]:
    """
    Batch crawl multiple URLs in parallel.
    
    Args:
        crawler: AsyncWebCrawler instance
        urls: List of URLs to crawl
        max_concurrent: Maximum concurrent connections
        memory_threshold_percent: Memory threshold for dispatcher
        check_interval: Check interval for dispatcher
        
    Returns:
        List of crawl results with URL and markdown content
    """
    from crawl4ai import CrawlerRunConfig, CacheMode
    
    print(f"[DEBUG] crawl_batch: Starting batch crawl for {len(urls)} URLs with max_concurrent={max_concurrent}")
    
    crawl_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, stream=False)
    dispatcher = build_dispatcher(max_concurrent, memory_threshold_percent, check_interval)
    
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


async def crawl_website_recursively(
    crawler,
    start_url: str,
    max_depth: int = 3,
    max_pages: int = 50,
    delay: float = 1.0
) -> List[Dict[str, Any]]:
    """
    Crawl a website recursively, one page at a time with proper domain filtering and error handling.
    
    Args:
        crawler: The AsyncWebCrawler instance
        start_url: The starting URL to crawl
        max_depth: Maximum depth to crawl (default: 3)
        max_pages: Maximum number of pages to crawl (default: 50)
        delay: Delay between requests in seconds (default: 1.0)
    
    Returns:
        List of dictionaries containing URL and markdown content
    """
    from crawl4ai import CrawlerRunConfig, CacheMode
    
    visited = set()
    results = []
    to_crawl = [(start_url, 0)]  # (url, depth)
    base_domain = urlparse(start_url).netloc
    
    print(f"[INFO] Starting recursive crawl of {start_url} (max_depth={max_depth}, max_pages={max_pages})")
    
    while to_crawl and len(results) < max_pages:
        url, depth = to_crawl.pop(0)
        
        # Skip if already visited or depth exceeded
        if url in visited or depth > max_depth:
            continue
            
        visited.add(url)
        
        try:
            print(f"[INFO] Crawling [{len(results)+1}/{max_pages}] depth={depth}: {url}")
            
            # Configure crawler for single page
            run_config = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                stream=False,
                word_count_threshold=10
            )
            
            result = await crawler.arun(url=url, config=run_config)
            
            # Add delay between requests to be respectful
            if delay > 0:
                await asyncio.sleep(delay)
            
            if not result.success:
                print(f"[WARNING] Failed to crawl {url}: {result.error_message}")
                continue
                
            # Extract content - prefer markdown, fall back to HTML conversion
            content = result.markdown
            if not content and hasattr(result, 'html') and result.html:
                try:
                    content = html2text.html2text(result.html)
                except Exception as e:
                    print(f"[ERROR] Failed to convert HTML to markdown for {url}: {e}")
                    continue
            
            if not content or len(content.strip()) < 50:
                print(f"[WARNING] No meaningful content found for {url}")
                continue
                
            # Store successful result
            results.append({
                "url": url,
                "markdown": content,
                "depth": depth,
                "title": getattr(result, 'title', '') or '',
                "word_count": len(content.split())
            })
            
            print(f"[SUCCESS] Crawled {url} - {len(content)} chars, {len(content.split())} words")
            
            # Extract and queue internal links for next depth level
            if depth < max_depth and hasattr(result, 'links'):
                internal_links = result.links.get("internal", [])
                queued_count = 0
                
                for link_info in internal_links:
                    if isinstance(link_info, dict) and "href" in link_info:
                        link_url = link_info["href"]
                    elif isinstance(link_info, str):
                        link_url = link_info
                    else:
                        continue
                        
                    # Resolve relative URLs
                    absolute_url = urljoin(url, link_url)
                    
                    # Remove fragments
                    absolute_url = urldefrag(absolute_url)[0]
                    
                    # Filter by domain and avoid duplicates
                    link_domain = urlparse(absolute_url).netloc
                    if (link_domain == base_domain and 
                        absolute_url not in visited and 
                        absolute_url not in [u for u, d in to_crawl]):
                        to_crawl.append((absolute_url, depth + 1))
                        queued_count += 1
                        
                print(f"[INFO] Found {len(internal_links)} internal links, queued {queued_count} new URLs")
                
        except Exception as e:
            print(f"[ERROR] Exception while crawling {url}: {e}")
            continue
    
    print(f"[INFO] Recursive crawl completed. Crawled {len(results)} pages from {start_url}")
    return results 