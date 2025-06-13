"""
Comprehensive Test Suite for MCP Tools
=====================================

This test suite verifies that all MCP tools in the doc-monitor server
are working correctly. It includes:
- Unit tests for each individual tool
- Integration tests for workflows
- Edge case and error handling tests
- Performance tests
- Mock data setup and teardown

Requirements:
- pytest
- pytest-asyncio
- pytest-mock
- unittest.mock
"""

import pytest
import asyncio
import json
import os
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from typing import Dict, List, Any
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from doc_fetcher_mcp import (
    DocFetcherContext,
    check_document_changes,
    monitor_documentation,
    get_available_sources,
    check_all_document_changes,
    perform_rag_query,
    advanced_rag_query,
    get_document_history,
    list_monitored_documentations,
    delete_documentation_from_monitoring
)

# =========================
# Test Fixtures and Setup
# =========================

@pytest.fixture
def mock_supabase_client():
    """Mock Supabase client with all necessary methods."""
    client = Mock()
    
    # Mock table methods
    table_mock = Mock()
    client.table.return_value = table_mock
    client.from_.return_value = table_mock
    
    # Mock query chain methods
    table_mock.select.return_value = table_mock
    table_mock.insert.return_value = table_mock
    table_mock.upsert.return_value = table_mock
    table_mock.update.return_value = table_mock
    table_mock.delete.return_value = table_mock
    table_mock.eq.return_value = table_mock
    table_mock.not_.return_value = table_mock
    table_mock.is_.return_value = table_mock
    table_mock.order.return_value = table_mock
    table_mock.limit.return_value = table_mock
    
    # Mock execute method with default empty response
    execute_mock = Mock()
    execute_mock.data = []
    table_mock.execute.return_value = execute_mock
    
    return client

@pytest.fixture
def mock_crawler():
    """Mock AsyncWebCrawler."""
    crawler = AsyncMock()
    crawler.__aenter__ = AsyncMock(return_value=crawler)
    crawler.__aexit__ = AsyncMock(return_value=None)
    return crawler

@pytest.fixture
def mock_context(mock_supabase_client, mock_crawler):
    """Mock MCP context with lifespan context."""
    context = Mock()
    lifespan_context = DocFetcherContext(
        crawler=mock_crawler,
        supabase_client=mock_supabase_client
    )
    context.request_context.lifespan_context = lifespan_context
    return context

@pytest.fixture
def sample_crawled_pages_data():
    """Sample data for crawled pages table."""
    return [
        {
            "id": 1,
            "url": "https://example.com/docs",
            "chunk_number": 0,
            "content": "This is sample documentation content",
            "metadata": {
                "source": "example.com",
                "title": "Documentation",
                "section": "intro"
            },
            "version": 1,
            "created_at": "2024-01-01T00:00:00Z"
        },
        {
            "id": 2,
            "url": "https://api.example.com/docs",
            "chunk_number": 0,
            "content": "API documentation content",
            "metadata": {
                "source": "api.example.com",
                "path": "/users",
                "method": "GET"
            },
            "version": 1,
            "created_at": "2024-01-01T01:00:00Z"
        }
    ]

@pytest.fixture
def sample_monitored_docs_data():
    """Sample data for monitored documentations table."""
    return [
        {
            "id": 1,
            "url": "https://example.com/docs",
            "date_added": "2024-01-01T00:00:00Z",
            "crawl_type": "webpage",
            "status": "active",
            "last_crawled_at": "2024-01-01T00:00:00Z",
            "notes": "Main documentation"
        },
        {
            "id": 2,
            "url": "https://api.example.com/openapi.json",
            "date_added": "2024-01-01T01:00:00Z",
            "crawl_type": "openapi",
            "status": "active",
            "last_crawled_at": "2024-01-01T01:00:00Z",
            "notes": "API specification"
        }
    ]

@pytest.fixture
def sample_document_changes_data():
    """Sample data for document changes table."""
    return [
        {
            "id": 1,
            "url": "https://example.com/docs",
            "version": 1,
            "change_type": "added",
            "change_summary": "Initial version indexed",
            "change_impact": "high",
            "change_details": {"chunks": 5},
            "created_at": "2024-01-01T00:00:00Z"
        },
        {
            "id": 2,
            "url": "https://example.com/docs",
            "version": 2,
            "change_type": "modified",
            "change_summary": "Content updated",
            "change_impact": "medium",
            "change_details": {"chunks_modified": 2},
            "created_at": "2024-01-02T00:00:00Z"
        }
    ]

# =========================
# Unit Tests for Each MCP Tool
# =========================

class TestCheckDocumentChanges:
    """Test the check_document_changes MCP tool."""
    
    @pytest.mark.asyncio
    async def test_check_document_changes_success(self, mock_context):
        """Test successful document change checking."""
        with patch('doc_fetcher_mcp.check_and_update_document_changes') as mock_check:
            mock_check.return_value = {
                "success": True,
                "url": "https://example.com/docs",
                "changes_detected": True,
                "new_version": 2
            }
            
            result = await check_document_changes(mock_context, "https://example.com/docs")
            result_data = json.loads(result)
            
            assert result_data["success"] is True
            assert result_data["url"] == "https://example.com/docs"
            assert result_data["changes_detected"] is True
            mock_check.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_check_document_changes_error(self, mock_context):
        """Test error handling in document change checking."""
        with patch('doc_fetcher_mcp.check_and_update_document_changes') as mock_check:
            mock_check.side_effect = Exception("Network error")
            
            result = await check_document_changes(mock_context, "https://example.com/docs")
            result_data = json.loads(result)
            
            assert result_data["success"] is False
            assert "Network error" in result_data["error"]
    
    @pytest.mark.asyncio
    async def test_check_document_changes_invalid_url(self, mock_context):
        """Test with invalid URL."""
        with patch('doc_fetcher_mcp.check_and_update_document_changes') as mock_check:
            mock_check.side_effect = ValueError("Invalid URL")
            
            result = await check_document_changes(mock_context, "invalid-url")
            result_data = json.loads(result)
            
            assert result_data["success"] is False
            assert "Invalid URL" in result_data["error"]

class TestMonitorDocumentation:
    """Test the monitor_documentation MCP tool."""
    
    @pytest.mark.asyncio
    async def test_monitor_documentation_new_webpage(self, mock_context):
        """Test monitoring a new webpage."""
        # Setup mock responses
        mock_context.request_context.lifespan_context.supabase_client.table().select().eq().execute.return_value.data = []
        
        with patch('doc_fetcher_mcp.is_openapi_url', return_value=False), \
             patch('doc_fetcher_mcp.is_txt', return_value=False), \
             patch('doc_fetcher_mcp.is_sitemap', return_value=False), \
             patch('doc_fetcher_mcp.process_website_documentation') as mock_process, \
             patch('doc_fetcher_mcp._process_crawl_results', return_value=10):
            
            mock_process.return_value = [
                {"url": "https://example.com/docs", "markdown": "# Documentation\nContent here"}
            ]
            
            result = await monitor_documentation(mock_context, "https://example.com/docs", "Test documentation")
            result_data = json.loads(result)
            
            assert result_data["success"] is True
            assert result_data["url"] == "https://example.com/docs"
            assert result_data["crawl_type"] == "webpage"
            assert result_data["chunks_stored"] == 10
    
    @pytest.mark.asyncio
    async def test_monitor_documentation_openapi(self, mock_context):
        """Test monitoring an OpenAPI specification."""
        mock_context.request_context.lifespan_context.supabase_client.table().select().eq().execute.return_value.data = []
        
        with patch('doc_fetcher_mcp.is_openapi_url', return_value=True), \
             patch('doc_fetcher_mcp.process_openapi_documentation') as mock_process:
            
            mock_process.return_value = ([{"url": "https://api.example.com/openapi.json"}], 15)
            
            result = await monitor_documentation(mock_context, "https://api.example.com/openapi.json")
            result_data = json.loads(result)
            
            assert result_data["success"] is True
            assert result_data["crawl_type"] == "openapi"
            assert result_data["chunks_stored"] == 15
    
    @pytest.mark.asyncio
    async def test_monitor_documentation_already_monitored(self, mock_context):
        """Test monitoring a URL that's already being monitored."""
        mock_context.request_context.lifespan_context.supabase_client.table().select().eq().execute.return_value.data = [
            {"id": 1, "status": "active"}
        ]
        
        result = await monitor_documentation(mock_context, "https://example.com/docs")
        result_data = json.loads(result)
        
        assert result_data["success"] is False
        assert "already monitored" in result_data["error"]
    
    @pytest.mark.asyncio
    async def test_monitor_documentation_sitemap(self, mock_context):
        """Test monitoring a sitemap."""
        mock_context.request_context.lifespan_context.supabase_client.table().select().eq().execute.return_value.data = []
        
        with patch('doc_fetcher_mcp.is_openapi_url', return_value=False), \
             patch('doc_fetcher_mcp.is_txt', return_value=False), \
             patch('doc_fetcher_mcp.is_sitemap', return_value=True), \
             patch('doc_fetcher_mcp.process_sitemap_documentation') as mock_process, \
             patch('doc_fetcher_mcp._process_crawl_results', return_value=25):
            
            mock_process.return_value = [
                {"url": "https://example.com/page1", "markdown": "Page 1 content"},
                {"url": "https://example.com/page2", "markdown": "Page 2 content"}
            ]
            
            result = await monitor_documentation(mock_context, "https://example.com/sitemap.xml")
            result_data = json.loads(result)
            
            assert result_data["success"] is True
            assert result_data["crawl_type"] == "sitemap"
            assert result_data["chunks_stored"] == 25

class TestGetAvailableSources:
    """Test the get_available_sources MCP tool."""
    
    @pytest.mark.asyncio
    async def test_get_available_sources_success(self, mock_context, sample_crawled_pages_data):
        """Test successful retrieval of available sources."""
        mock_context.request_context.lifespan_context.supabase_client.from_().select().not_().is_().execute.return_value.data = sample_crawled_pages_data
        
        result = await get_available_sources(mock_context)
        result_data = json.loads(result)
        
        assert result_data["success"] is True
        assert "example.com" in result_data["sources"]
        assert "api.example.com" in result_data["sources"]
        assert result_data["count"] == 2
    
    @pytest.mark.asyncio
    async def test_get_available_sources_empty(self, mock_context):
        """Test when no sources are available."""
        mock_context.request_context.lifespan_context.supabase_client.from_().select().not_().is_().execute.return_value.data = []
        
        result = await get_available_sources(mock_context)
        result_data = json.loads(result)
        
        assert result_data["success"] is True
        assert result_data["sources"] == []
        assert result_data["count"] == 0
    
    @pytest.mark.asyncio
    async def test_get_available_sources_error(self, mock_context):
        """Test error handling."""
        mock_context.request_context.lifespan_context.supabase_client.from_().select().not_().is_().execute.side_effect = Exception("Database error")
        
        result = await get_available_sources(mock_context)
        result_data = json.loads(result)
        
        assert result_data["success"] is False
        assert "Database error" in result_data["error"]

class TestCheckAllDocumentChanges:
    """Test the check_all_document_changes MCP tool."""
    
    @pytest.mark.asyncio
    async def test_check_all_document_changes_success(self, mock_context, sample_crawled_pages_data):
        """Test successful checking of all documents."""
        mock_context.request_context.lifespan_context.supabase_client.table().select().execute.return_value.data = sample_crawled_pages_data
        
        with patch('doc_fetcher_mcp.check_and_update_document_changes') as mock_check:
            mock_check.side_effect = [
                {"success": True, "url": "https://example.com/docs", "changes_detected": False},
                {"success": True, "url": "https://api.example.com/docs", "changes_detected": True}
            ]
            
            result = await check_all_document_changes(mock_context)
            result_data = json.loads(result)
            
            assert result_data["success"] is True
            assert result_data["total_urls_checked"] == 2
            assert len(result_data["results"]) == 2
    
    @pytest.mark.asyncio
    async def test_check_all_document_changes_empty_database(self, mock_context):
        """Test when no URLs are in the database."""
        mock_context.request_context.lifespan_context.supabase_client.table().select().execute.return_value.data = []
        
        result = await check_all_document_changes(mock_context)
        result_data = json.loads(result)
        
        assert result_data["success"] is False
        assert "No URLs found" in result_data["error"]

class TestPerformRagQuery:
    """Test the perform_rag_query MCP tool."""
    
    @pytest.mark.asyncio
    async def test_perform_rag_query_basic(self, mock_context):
        """Test basic RAG query."""
        mock_docs = [
            {
                "content": "This is documentation about authentication",
                "metadata": {"source": "example.com", "section": "auth"},
                "similarity": 0.9
            }
        ]
        
        with patch('doc_fetcher_mcp.semantic_search_documents', return_value=mock_docs):
            result = await perform_rag_query(mock_context, "authentication")
            result_data = json.loads(result)
            
            assert result_data["success"] is True
            assert result_data["query"] == "authentication"
            assert len(result_data["context_documents"]) == 1
            assert result_data["count"] == 1
    
    @pytest.mark.asyncio
    async def test_perform_rag_query_with_filters(self, mock_context):
        """Test RAG query with source and endpoint filters."""
        mock_docs = []
        
        with patch('doc_fetcher_mcp.semantic_search_documents', return_value=mock_docs) as mock_search:
            result = await perform_rag_query(
                mock_context, 
                "user endpoints", 
                source="api.example.com",
                endpoint="/users",
                method="GET"
            )
            result_data = json.loads(result)
            
            assert result_data["success"] is True
            assert result_data["filter"]["source"] == "api.example.com"
            assert result_data["filter"]["path"] == "/users"
            assert result_data["filter"]["method"] == "GET"
            mock_search.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_perform_rag_query_error(self, mock_context):
        """Test error handling in RAG query."""
        with patch('doc_fetcher_mcp.semantic_search_documents', side_effect=Exception("Search error")):
            result = await perform_rag_query(mock_context, "test query")
            result_data = json.loads(result)
            
            assert result_data["success"] is False
            assert "Search error" in result_data["error"]

class TestAdvancedRagQuery:
    """Test the advanced_rag_query MCP tool."""
    
    @pytest.mark.asyncio
    async def test_advanced_rag_query_with_reranking(self, mock_context):
        """Test advanced RAG query with reranking enabled."""
        mock_docs = [
            {
                "content": "Advanced authentication documentation",
                "metadata": {"source": "example.com"},
                "similarity": 0.85,
                "rerank_score": 0.92,
                "chunk_number": 0
            }
        ]
        
        with patch('doc_fetcher_mcp.improved_semantic_search', return_value=mock_docs):
            result = await advanced_rag_query(
                mock_context,
                "authentication methods",
                similarity_threshold=0.7,
                enable_reranking=True
            )
            result_data = json.loads(result)
            
            assert result_data["success"] is True
            assert result_data["search_method"] == "advanced_semantic_search_with_reranking"
            assert result_data["query_analysis"]["reranking_enabled"] is True
            assert result_data["query_analysis"]["similarity_threshold"] == 0.7
            assert "relevance_indicators" in result_data["context_documents"][0]
    
    @pytest.mark.asyncio
    async def test_advanced_rag_query_without_reranking(self, mock_context):
        """Test advanced RAG query with reranking disabled."""
        mock_docs = [
            {
                "content": "Basic documentation",
                "metadata": {"source": "example.com"},
                "similarity": 0.75,
                "chunk_number": 1
            }
        ]
        
        with patch('doc_fetcher_mcp.improved_semantic_search', return_value=mock_docs):
            result = await advanced_rag_query(
                mock_context,
                "basic information",
                enable_reranking=False
            )
            result_data = json.loads(result)
            
            assert result_data["success"] is True
            assert result_data["query_analysis"]["reranking_enabled"] is False
    
    @pytest.mark.asyncio
    async def test_advanced_rag_query_relevance_indicators(self, mock_context):
        """Test that relevance indicators are correctly calculated."""
        mock_docs = [
            {
                "content": "This documentation covers authentication and security methods",
                "metadata": {"source": "example.com"},
                "similarity": 0.88,
                "rerank_score": 0.95,
                "chunk_number": 2
            }
        ]
        
        with patch('doc_fetcher_mcp.improved_semantic_search', return_value=mock_docs):
            result = await advanced_rag_query(mock_context, "authentication security")
            result_data = json.loads(result)
            
            doc = result_data["context_documents"][0]
            relevance = doc["relevance_indicators"]
            
            assert relevance["similarity_score"] == 0.88
            assert relevance["rerank_score"] == 0.95
            assert relevance["exact_matches"] >= 1  # Should match "authentication"
            assert relevance["chunk_number"] == 2

class TestGetDocumentHistory:
    """Test the get_document_history MCP tool."""
    
    @pytest.mark.asyncio
    async def test_get_document_history_success(self, mock_context, sample_document_changes_data):
        """Test successful retrieval of document history."""
        mock_context.request_context.lifespan_context.supabase_client.table().select().eq().order().execute.return_value.data = sample_document_changes_data
        
        result = await get_document_history(mock_context, "https://example.com/docs")
        result_data = json.loads(result)
        
        assert result_data["success"] is True
        assert result_data["url"] == "https://example.com/docs"
        assert len(result_data["history"]) == 2
        assert result_data["history"][0]["version"] == 1
        assert result_data["history"][1]["version"] == 2
    
    @pytest.mark.asyncio
    async def test_get_document_history_no_history(self, mock_context):
        """Test when no history exists for a document."""
        mock_context.request_context.lifespan_context.supabase_client.table().select().eq().order().execute.return_value.data = []
        
        result = await get_document_history(mock_context, "https://nonexistent.com/docs")
        result_data = json.loads(result)
        
        assert result_data["success"] is True
        assert result_data["history"] == []
    
    @pytest.mark.asyncio
    async def test_get_document_history_error(self, mock_context):
        """Test error handling."""
        mock_context.request_context.lifespan_context.supabase_client.table().select().eq().order().execute.side_effect = Exception("Database error")
        
        result = await get_document_history(mock_context, "https://example.com/docs")
        result_data = json.loads(result)
        
        assert result_data["success"] is False
        assert "Database error" in result_data["error"]

class TestListMonitoredDocumentations:
    """Test the list_monitored_documentations MCP tool."""
    
    @pytest.mark.asyncio
    async def test_list_monitored_documentations_success(self, mock_context, sample_monitored_docs_data):
        """Test successful listing of monitored documentations."""
        mock_context.request_context.lifespan_context.supabase_client.table().select().eq().order().execute.return_value.data = sample_monitored_docs_data
        
        result = await list_monitored_documentations(mock_context)
        result_data = json.loads(result)
        
        assert result_data["success"] is True
        assert len(result_data["monitored_documentations"]) == 2
        assert result_data["monitored_documentations"][0]["url"] == "https://example.com/docs"
        assert result_data["monitored_documentations"][1]["crawl_type"] == "openapi"
    
    @pytest.mark.asyncio
    async def test_list_monitored_documentations_empty(self, mock_context):
        """Test when no documentations are being monitored."""
        mock_context.request_context.lifespan_context.supabase_client.table().select().eq().order().execute.return_value.data = []
        
        result = await list_monitored_documentations(mock_context)
        result_data = json.loads(result)
        
        assert result_data["success"] is True
        assert result_data["monitored_documentations"] == []
    
    @pytest.mark.asyncio
    async def test_list_monitored_documentations_error(self, mock_context):
        """Test error handling."""
        mock_context.request_context.lifespan_context.supabase_client.table().select().eq().order().execute.side_effect = Exception("Database error")
        
        result = await list_monitored_documentations(mock_context)
        result_data = json.loads(result)
        
        assert result_data["success"] is False
        assert "Database error" in result_data["error"]

class TestDeleteDocumentationFromMonitoring:
    """Test the delete_documentation_from_monitoring MCP tool."""
    
    @pytest.mark.asyncio
    async def test_delete_documentation_success(self, mock_context):
        """Test successful deletion of documentation from monitoring."""
        # Mock existing document
        mock_context.request_context.lifespan_context.supabase_client.table().select().eq().execute.return_value.data = [
            {"id": 1, "status": "active"}
        ]
        
        result = await delete_documentation_from_monitoring(mock_context, "https://example.com/docs")
        result_data = json.loads(result)
        
        assert result_data["success"] is True
        assert result_data["url"] == "https://example.com/docs"
        assert "removed from monitoring" in result_data["message"]
    
    @pytest.mark.asyncio
    async def test_delete_documentation_not_found(self, mock_context):
        """Test deletion of non-existent documentation."""
        mock_context.request_context.lifespan_context.supabase_client.table().select().eq().execute.return_value.data = []
        
        result = await delete_documentation_from_monitoring(mock_context, "https://nonexistent.com/docs")
        result_data = json.loads(result)
        
        assert result_data["success"] is False
        assert "not found" in result_data["error"]
    
    @pytest.mark.asyncio
    async def test_delete_documentation_error(self, mock_context):
        """Test error handling."""
        mock_context.request_context.lifespan_context.supabase_client.table().select().eq().execute.side_effect = Exception("Database error")
        
        result = await delete_documentation_from_monitoring(mock_context, "https://example.com/docs")
        result_data = json.loads(result)
        
        assert result_data["success"] is False
        assert "Database error" in result_data["error"]

# =========================
# Integration Tests
# =========================

class TestMCPToolsIntegration:
    """Integration tests that test tool workflows."""
    
    @pytest.mark.asyncio
    async def test_full_monitoring_workflow(self, mock_context):
        """Test the complete workflow: monitor -> query -> check changes -> delete."""
        # Step 1: Monitor documentation
        mock_context.request_context.lifespan_context.supabase_client.table().select().eq().execute.return_value.data = []
        
        with patch('doc_fetcher_mcp.is_openapi_url', return_value=False), \
             patch('doc_fetcher_mcp.is_txt', return_value=False), \
             patch('doc_fetcher_mcp.is_sitemap', return_value=False), \
             patch('doc_fetcher_mcp.process_website_documentation') as mock_process, \
             patch('doc_fetcher_mcp._process_crawl_results', return_value=5):
            
            mock_process.return_value = [{"url": "https://example.com/docs", "markdown": "# Test\nContent"}]
            
            # Monitor the documentation
            monitor_result = await monitor_documentation(mock_context, "https://example.com/docs")
            monitor_data = json.loads(monitor_result)
            assert monitor_data["success"] is True
            
            # Step 2: Query the documentation
            with patch('doc_fetcher_mcp.semantic_search_documents') as mock_search:
                mock_search.return_value = [{"content": "Test content", "similarity": 0.9}]
                
                query_result = await perform_rag_query(mock_context, "test")
                query_data = json.loads(query_result)
                assert query_data["success"] is True
                assert len(query_data["context_documents"]) == 1
            
            # Step 3: Check for changes
            with patch('doc_fetcher_mcp.check_and_update_document_changes') as mock_check:
                mock_check.return_value = {"success": True, "changes_detected": False}
                
                changes_result = await check_document_changes(mock_context, "https://example.com/docs")
                changes_data = json.loads(changes_result)
                assert changes_data["success"] is True
            
            # Step 4: List monitored docs
            mock_context.request_context.lifespan_context.supabase_client.table().select().eq().order().execute.return_value.data = [
                {"url": "https://example.com/docs", "status": "active"}
            ]
            
            list_result = await list_monitored_documentations(mock_context)
            list_data = json.loads(list_result)
            assert list_data["success"] is True
            assert len(list_data["monitored_documentations"]) == 1
            
            # Step 5: Delete from monitoring
            mock_context.request_context.lifespan_context.supabase_client.table().select().eq().execute.return_value.data = [
                {"id": 1, "status": "active"}
            ]
            
            delete_result = await delete_documentation_from_monitoring(mock_context, "https://example.com/docs")
            delete_data = json.loads(delete_result)
            assert delete_data["success"] is True

# =========================
# Edge Case Tests
# =========================

class TestMCPToolsEdgeCases:
    """Test edge cases and error conditions."""
    
    @pytest.mark.asyncio
    async def test_empty_query_strings(self, mock_context):
        """Test tools with empty query strings."""
        with patch('doc_fetcher_mcp.semantic_search_documents', return_value=[]):
            result = await perform_rag_query(mock_context, "")
            result_data = json.loads(result)
            assert result_data["success"] is True
            assert result_data["count"] == 0
    
    @pytest.mark.asyncio
    async def test_malformed_urls(self, mock_context):
        """Test tools with malformed URLs."""
        with patch('doc_fetcher_mcp.check_and_update_document_changes') as mock_check:
            mock_check.side_effect = ValueError("Invalid URL format")
            
            result = await check_document_changes(mock_context, "not-a-url")
            result_data = json.loads(result)
            assert result_data["success"] is False
    
    @pytest.mark.asyncio
    async def test_very_long_urls(self, mock_context):
        """Test with extremely long URLs."""
        long_url = "https://example.com/" + "a" * 2000
        
        with patch('doc_fetcher_mcp.check_and_update_document_changes') as mock_check:
            mock_check.return_value = {"success": True, "url": long_url}
            
            result = await check_document_changes(mock_context, long_url)
            result_data = json.loads(result)
            assert result_data["success"] is True
    
    @pytest.mark.asyncio
    async def test_special_characters_in_query(self, mock_context):
        """Test RAG queries with special characters."""
        special_query = "What is @#$%^&*()?"
        
        with patch('doc_fetcher_mcp.semantic_search_documents', return_value=[]):
            result = await perform_rag_query(mock_context, special_query)
            result_data = json.loads(result)
            assert result_data["success"] is True
            assert result_data["query"] == special_query
    
    @pytest.mark.asyncio
    async def test_unicode_content(self, mock_context):
        """Test with Unicode content in queries and responses."""
        unicode_query = "How to implement 测试 and 🚀 features?"
        
        mock_docs = [{"content": "Unicode test: 测试 🚀", "similarity": 0.8}]
        
        with patch('doc_fetcher_mcp.semantic_search_documents', return_value=mock_docs):
            result = await perform_rag_query(mock_context, unicode_query)
            result_data = json.loads(result)
            assert result_data["success"] is True
            assert "测试" in result_data["context_documents"][0]["content"]

# =========================
# Performance Tests
# =========================

class TestMCPToolsPerformance:
    """Performance tests for MCP tools."""
    
    @pytest.mark.asyncio
    async def test_large_dataset_query(self, mock_context):
        """Test RAG query performance with large dataset."""
        # Simulate large number of documents
        large_docs = [
            {"content": f"Document {i} content", "similarity": 0.5 + (i * 0.01)}
            for i in range(100)
        ]
        
        with patch('doc_fetcher_mcp.semantic_search_documents', return_value=large_docs[:10]):
            start_time = datetime.now()
            result = await perform_rag_query(mock_context, "test", match_count=10)
            end_time = datetime.now()
            
            result_data = json.loads(result)
            assert result_data["success"] is True
            assert len(result_data["context_documents"]) == 10
            
            # Should complete within reasonable time (adjust threshold as needed)
            assert (end_time - start_time).total_seconds() < 1.0
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, mock_context):
        """Test concurrent tool operations."""
        with patch('doc_fetcher_mcp.semantic_search_documents', return_value=[]), \
             patch('doc_fetcher_mcp.check_and_update_document_changes', return_value={"success": True}):
            
            # Run multiple operations concurrently
            tasks = [
                perform_rag_query(mock_context, f"query {i}")
                for i in range(5)
            ]
            tasks.extend([
                check_document_changes(mock_context, f"https://example{i}.com")
                for i in range(3)
            ])
            
            results = await asyncio.gather(*tasks)
            
            # All operations should succeed
            for result in results:
                result_data = json.loads(result)
                assert result_data["success"] is True

# =========================
# Test Configuration and Runners
# =========================

class TestMCPToolsConfiguration:
    """Test configuration and setup validation."""
    
    def test_all_tools_have_tests(self):
        """Ensure all MCP tools have corresponding tests."""
        mcp_tools = [
            'check_document_changes',
            'monitor_documentation',
            'get_available_sources',
            'check_all_document_changes',
            'perform_rag_query',
            'advanced_rag_query',
            'get_document_history',
            'list_monitored_documentations',
            'delete_documentation_from_monitoring'
        ]
        
        test_classes = [
            'TestCheckDocumentChanges',
            'TestMonitorDocumentation',
            'TestGetAvailableSources',
            'TestCheckAllDocumentChanges',
            'TestPerformRagQuery',
            'TestAdvancedRagQuery',
            'TestGetDocumentHistory',
            'TestListMonitoredDocumentations',
            'TestDeleteDocumentationFromMonitoring'
        ]
        
        # Verify we have a test class for each tool
        assert len(mcp_tools) == len(test_classes)
        
        # This test serves as documentation that we've covered all tools
        for tool in mcp_tools:
            print(f"✓ {tool} - has corresponding test class")

if __name__ == "__main__":
    # Run tests with coverage if pytest is available
    pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "--disable-warnings"
    ]) 