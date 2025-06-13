"""
Main utility module for the doc-monitor MCP server.
This module imports and exposes all utility functions from the modular components.
"""

# Database operations
from database import (
    get_supabase_client,
    batch_upsert_documents
)

# AI embeddings and contextual processing
from embeddings import (
    batch_create_embeddings,
    create_single_embedding,
    contextualize_chunk,
    contextualize_chunk_worker
)

# Search and RAG functionality
from search import (
    semantic_search_documents,
    improved_semantic_search
)

# Web crawling operations
from crawling import (
    crawl_markdown_file,
    build_dispatcher,
    crawl_batch,
    crawl_website_recursively
)

# Document processing and text operations
from processing import (
    smart_chunk_markdown,
    semantic_chunk_markdown,
    extract_section_info,
    build_metadata,
    analyze_change_impact
)

# URL utilities
from url_utils import (
    is_openapi_url,
    is_sitemap,
    is_txt,
    parse_sitemap,
    get_domain,
    normalize_url,
    is_same_domain
)

# OpenAPI specification handling
from openapi import (
    fetch_openapi_spec,
    openapi_spec_to_markdown_chunks,
    extract_openapi_info
)

# High-level document workflows
from document_workflows import (
    process_openapi_documentation,
    process_sitemap_documentation,
    process_text_file_documentation,
    process_website_documentation,
    check_and_update_document_changes,
    create_crawl_summary
)

# Export all functions for backward compatibility
__all__ = [
    # Database
    'get_supabase_client',
    'batch_upsert_documents',
    
    # Embeddings
    'batch_create_embeddings',
    'create_single_embedding',
    'contextualize_chunk',
    'contextualize_chunk_worker',
    
    # Search
    'semantic_search_documents',
    'improved_semantic_search',
    
    # Crawling
    'crawl_markdown_file',
    'build_dispatcher',
    'crawl_batch',
    'crawl_website_recursively',
    
    # Processing
    'smart_chunk_markdown',
    'semantic_chunk_markdown',
    'extract_section_info',
    'build_metadata',
    'analyze_change_impact',
    
    # URL utilities
    'is_openapi_url',
    'is_sitemap',
    'is_txt',
    'parse_sitemap',
    'get_domain',
    'normalize_url',
    'is_same_domain',
    
    # OpenAPI
    'fetch_openapi_spec',
    'openapi_spec_to_markdown_chunks',
    'extract_openapi_info',
    
    # Workflows
    'process_openapi_documentation',
    'process_sitemap_documentation',
    'process_text_file_documentation',
    'process_website_documentation',
    'check_and_update_document_changes',
    'create_crawl_summary'
] 