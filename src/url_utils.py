"""
URL utilities for the doc-monitor MCP server.
Handles URL detection, sitemap parsing, and URL-related operations.
"""
from typing import List, Optional
from urllib.parse import urlparse
import requests
from xml.etree import ElementTree


def is_openapi_url(url: str) -> bool:
    """
    Return True if the URL is likely an OpenAPI spec (json/yaml).
    
    Args:
        url: URL to check
        
    Returns:
        True if URL appears to be an OpenAPI specification
    """
    lowered = url.lower()
    return lowered.endswith('.json') or lowered.endswith('.yaml') or lowered.endswith('.yml')


def is_sitemap(url: str) -> bool:
    """
    Return True if the URL is a sitemap.
    
    Args:
        url: URL to check
        
    Returns:
        True if URL appears to be a sitemap
    """
    return url.endswith('sitemap.xml') or 'sitemap' in urlparse(url).path


def is_txt(url: str) -> bool:
    """
    Return True if the URL is a text file.
    
    Args:
        url: URL to check
        
    Returns:
        True if URL appears to be a text file
    """
    return url.endswith('.txt')


def parse_sitemap(sitemap_url: str) -> List[str]:
    """
    Parse a sitemap and extract URLs as a list of strings.
    
    Args:
        sitemap_url: URL of the sitemap to parse
        
    Returns:
        List of URLs found in the sitemap
    """
    try:
        resp = requests.get(sitemap_url)
        if resp.status_code != 200:
            print(f"Failed to fetch sitemap {sitemap_url}: HTTP {resp.status_code}")
            return []
        
        tree = ElementTree.fromstring(resp.content)
        urls = [loc.text for loc in tree.findall('.//{*}loc') if loc.text]
        
        print(f"[INFO] Parsed sitemap {sitemap_url}: found {len(urls)} URLs")
        return urls
        
    except Exception as e:
        print(f"Error parsing sitemap XML: {e}")
        return []


def get_domain(url: str) -> str:
    """
    Extract the domain from a URL.
    
    Args:
        url: URL to extract domain from
        
    Returns:
        Domain name
    """
    return urlparse(url).netloc


def normalize_url(url: str) -> str:
    """
    Normalize a URL by removing fragments and trailing slashes.
    
    Args:
        url: URL to normalize
        
    Returns:
        Normalized URL
    """
    parsed = urlparse(url)
    # Remove fragment and trailing slash
    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    if normalized.endswith('/') and len(parsed.path) > 1:
        normalized = normalized[:-1]
    return normalized


def is_same_domain(url1: str, url2: str) -> bool:
    """
    Check if two URLs are from the same domain.
    
    Args:
        url1: First URL
        url2: Second URL
        
    Returns:
        True if URLs are from the same domain
    """
    return get_domain(url1) == get_domain(url2) 