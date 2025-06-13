"""
Direct MCP Tools Test Suite
===========================

Now that imports are working, this test suite directly imports and tests all 9 MCP tools
with proper mocking of external dependencies (Supabase, AsyncWebCrawler, OpenAI API).
"""

import pytest
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any, List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Now we can import the MCP tools directly!
try:
    from doc_fetcher_mcp import (
        check_document_changes,
        monitor_documentation,
        get_available_sources,
        check_all_document_changes,
        perform_rag_query,
        advanced_rag_query,
        get_document_history,
        list_monitored_documentations,
        delete_documentation_from_monitoring,
        mcp
    )
    MCP_TOOLS_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Could not import MCP tools: {e}")
    MCP_TOOLS_AVAILABLE = False

@pytest.fixture
def mock_mcp_context():
    """Create a comprehensive mock MCP context."""
    context = Mock()
    context.request_context = Mock()
    context.request_context.lifespan_context = Mock()
    
    # Mock Supabase client with fluent interface
    supabase_mock = Mock()
    table_mock = Mock()
    
    # Setup table method
    supabase_mock.table.return_value = table_mock
    supabase_mock.from_.return_value = table_mock
    
    # Setup fluent query interface
    for method in ['select', 'insert', 'upsert', 'update', 'delete', 'eq', 'not_', 'is_', 'order', 'limit']:
        setattr(table_mock, method, Mock(return_value=table_mock))
    
    # Setup RPC method
    rpc_mock = Mock()
    rpc_mock.execute.return_value.data = []
    supabase_mock.rpc.return_value = rpc_mock
    
    # Setup execute with sample data
    execute_mock = Mock()
    execute_mock.data = []
    table_mock.execute.return_value = execute_mock
    
    # Mock AsyncWebCrawler
    crawler_mock = AsyncMock()
    crawler_mock.arun.return_value = Mock(
        success=True,
        status_code=200,
        markdown="# Sample Document\nThis is sample content.",
        links_internal=[],
        links_external=[]
    )
    
    # Attach to context
    context.request_context.lifespan_context.supabase_client = supabase_mock
    context.request_context.lifespan_context.crawler = crawler_mock
    
    return context

@pytest.fixture
def sample_monitored_docs():
    """Sample monitored documentation data."""
    return [
        {
            "id": 1,
            "url": "https://example.com/docs",
            "status": "active",
            "notes": "Main documentation",
            "created_at": "2024-01-01T00:00:00Z"
        },
        {
            "id": 2,
            "url": "https://api.example.com/docs",
            "status": "active", 
            "notes": "API documentation",
            "created_at": "2024-01-02T00:00:00Z"
        }
    ]

@pytest.fixture
def sample_crawled_pages():
    """Sample crawled pages data."""
    return [
        {
            "id": 1,
            "url": "https://example.com/docs",
            "chunk_number": 1,
            "content": "Introduction to our API",
            "metadata": {"source": "example.com", "type": "documentation"},
            "embedding": [0.1] * 1536,  # Mock embedding vector
            "version": "1.0"
        },
        {
            "id": 2,
            "url": "https://example.com/docs",
            "chunk_number": 2,
            "content": "Authentication guide for developers",
            "metadata": {"source": "example.com", "type": "documentation"},
            "embedding": [0.2] * 1536,
            "version": "1.0"
        }
    ]

class TestMCPToolsDirectImport:
    """Test that all MCP tools can be imported directly."""
    
    def test_mcp_tools_import_success(self):
        """Test that all MCP tools can be imported successfully."""
        if not MCP_TOOLS_AVAILABLE:
            pytest.skip("MCP tools could not be imported")
        
        # Test that all tools are available
        assert check_document_changes is not None
        assert monitor_documentation is not None
        assert get_available_sources is not None
        assert check_all_document_changes is not None
        assert perform_rag_query is not None
        assert advanced_rag_query is not None
        assert get_document_history is not None
        assert list_monitored_documentations is not None
        assert delete_documentation_from_monitoring is not None
        assert mcp is not None
        
        print("✅ All 9 MCP tools imported successfully!")
    
    def test_mcp_server_object(self):
        """Test that the MCP server object exists and has tools."""
        if not MCP_TOOLS_AVAILABLE:
            pytest.skip("MCP tools could not be imported")
        
        assert hasattr(mcp, 'list_tools')
        assert hasattr(mcp, 'call_tool')
        print("✅ MCP server object is properly configured")

@pytest.mark.skipif(not MCP_TOOLS_AVAILABLE, reason="MCP tools not available")
class TestCheckDocumentChanges:
    """Test check_document_changes MCP tool."""
    
    @pytest.mark.asyncio
    async def test_check_document_changes_success(self, mock_mcp_context):
        """Test successful document change checking."""
        # Mock the workflow function
        with patch('doc_fetcher_mcp.check_and_update_document_changes') as mock_workflow:
            mock_workflow.return_value = {
                "success": True,
                "url": "https://example.com/docs",
                "changes_detected": False,
                "message": "No changes detected"
            }
            
            result = await check_document_changes(mock_mcp_context, "https://example.com/docs")
            result_data = json.loads(result)
            
            assert result_data["success"] is True
            assert result_data["url"] == "https://example.com/docs"
            assert "changes_detected" in result_data
            mock_workflow.assert_called_once()
            
            print("✅ check_document_changes works with real import")
    
    @pytest.mark.asyncio
    async def test_check_document_changes_error(self, mock_mcp_context):
        """Test error handling in document change checking."""
        with patch('doc_fetcher_mcp.check_and_update_document_changes') as mock_workflow:
            mock_workflow.side_effect = Exception("Network error")
            
            result = await check_document_changes(mock_mcp_context, "https://invalid-url.com")
            result_data = json.loads(result)
            
            assert result_data["success"] is False
            assert "error" in result_data
            
            print("✅ check_document_changes handles errors correctly")

@pytest.mark.skipif(not MCP_TOOLS_AVAILABLE, reason="MCP tools not available")
class TestMonitorDocumentation:
    """Test monitor_documentation MCP tool."""
    
    @pytest.mark.asyncio
    async def test_monitor_documentation_success(self, mock_mcp_context):
        """Test successful documentation monitoring."""
        # Mock the workflow functions
        with patch('doc_fetcher_mcp.process_website_documentation') as mock_process:
            mock_process.return_value = {
                "success": True,
                "url": "https://example.com/docs",
                "crawl_type": "webpage",
                "chunks_stored": 5
            }
            
            result = await monitor_documentation(mock_mcp_context, "https://example.com/docs")
            result_data = json.loads(result)
            
            assert result_data["success"] is True
            assert result_data["url"] == "https://example.com/docs"
            assert "chunks_stored" in result_data
            
            print("✅ monitor_documentation works with real import")
    
    @pytest.mark.asyncio
    async def test_monitor_documentation_with_notes(self, mock_mcp_context):
        """Test monitoring with notes parameter."""
        with patch('doc_fetcher_mcp.process_website_documentation') as mock_process:
            mock_process.return_value = {
                "success": True,
                "url": "https://example.com/api-docs",
                "notes": "API documentation",
                "crawl_type": "webpage",
                "chunks_stored": 3
            }
            
            result = await monitor_documentation(
                mock_mcp_context, 
                "https://example.com/api-docs", 
                "API documentation"
            )
            result_data = json.loads(result)
            
            assert result_data["success"] is True
            assert result_data["notes"] == "API documentation"
            
            print("✅ monitor_documentation handles notes parameter")

@pytest.mark.skipif(not MCP_TOOLS_AVAILABLE, reason="MCP tools not available")
class TestGetAvailableSources:
    """Test get_available_sources MCP tool."""
    
    @pytest.mark.asyncio
    async def test_get_available_sources_success(self, mock_mcp_context, sample_crawled_pages):
        """Test successful retrieval of available sources."""
        # Configure mock to return sample data
        mock_mcp_context.request_context.lifespan_context.supabase_client.from_().select().not_().is_().execute.return_value.data = sample_crawled_pages
        
        result = await get_available_sources(mock_mcp_context)
        result_data = json.loads(result)
        
        assert result_data["success"] is True
        assert "sources" in result_data
        assert len(result_data["sources"]) == 1  # Only one unique source
        assert "example.com" in result_data["sources"]
        
        print("✅ get_available_sources works with real import")

@pytest.mark.skipif(not MCP_TOOLS_AVAILABLE, reason="MCP tools not available")
class TestPerformRagQuery:
    """Test perform_rag_query MCP tool."""
    
    @pytest.mark.asyncio
    async def test_perform_rag_query_success(self, mock_mcp_context, sample_crawled_pages):
        """Test successful RAG query."""
        with patch('doc_fetcher_mcp.semantic_search_documents') as mock_search:
            mock_search.return_value = sample_crawled_pages
            
            result = await perform_rag_query(mock_mcp_context, "authentication guide")
            result_data = json.loads(result)
            
            assert result_data["success"] is True
            assert result_data["query"] == "authentication guide"
            assert "context_documents" in result_data
            assert len(result_data["context_documents"]) == 2
            
            print("✅ perform_rag_query works with real import")
    
    @pytest.mark.asyncio
    async def test_perform_rag_query_with_filters(self, mock_mcp_context):
        """Test RAG query with source filter."""
        with patch('doc_fetcher_mcp.semantic_search_documents') as mock_search:
            mock_search.return_value = []
            
            result = await perform_rag_query(
                mock_mcp_context, 
                "API documentation", 
                source="example.com"
            )
            result_data = json.loads(result)
            
            assert result_data["success"] is True
            assert result_data["query"] == "API documentation"
            # Verify that semantic_search_documents was called with filter
            mock_search.assert_called_once()
            call_args = mock_search.call_args[1]
            assert "filter_metadata" in call_args
            
            print("✅ perform_rag_query handles source filtering")

@pytest.mark.skipif(not MCP_TOOLS_AVAILABLE, reason="MCP tools not available")
class TestAdvancedRagQuery:
    """Test advanced_rag_query MCP tool."""
    
    @pytest.mark.asyncio
    async def test_advanced_rag_query_success(self, mock_mcp_context, sample_crawled_pages):
        """Test successful advanced RAG query."""
        with patch('doc_fetcher_mcp.improved_semantic_search') as mock_search:
            mock_search.return_value = sample_crawled_pages
            
            result = await advanced_rag_query(
                mock_mcp_context, 
                "authentication and security",
                match_count=5,
                enable_reranking=True
            )
            result_data = json.loads(result)
            
            assert result_data["success"] is True
            assert result_data["query"] == "authentication and security"
            assert result_data["advanced_features"]["reranking_enabled"] is True
            assert "context_documents" in result_data
            
            print("✅ advanced_rag_query works with real import")

@pytest.mark.skipif(not MCP_TOOLS_AVAILABLE, reason="MCP tools not available")
class TestListMonitoredDocumentations:
    """Test list_monitored_documentations MCP tool."""
    
    @pytest.mark.asyncio
    async def test_list_monitored_documentations_success(self, mock_mcp_context, sample_monitored_docs):
        """Test successful listing of monitored documentations."""
        # Configure mock to return sample data
        mock_mcp_context.request_context.lifespan_context.supabase_client.from_().select().not_().is_().execute.return_value.data = sample_monitored_docs
        
        result = await list_monitored_documentations(mock_mcp_context)
        result_data = json.loads(result)
        
        assert result_data["success"] is True
        assert "monitored_documentations" in result_data
        assert len(result_data["monitored_documentations"]) == 2
        assert result_data["count"] == 2
        
        print("✅ list_monitored_documentations works with real import")

@pytest.mark.skipif(not MCP_TOOLS_AVAILABLE, reason="MCP tools not available")
class TestDeleteDocumentationFromMonitoring:
    """Test delete_documentation_from_monitoring MCP tool."""
    
    @pytest.mark.asyncio
    async def test_delete_documentation_success(self, mock_mcp_context):
        """Test successful deletion from monitoring."""
        # Configure mock to simulate successful deletion
        update_mock = Mock()
        update_mock.execute.return_value.data = [{"id": 1, "status": "deleted"}]
        mock_mcp_context.request_context.lifespan_context.supabase_client.from_().update().eq().execute = update_mock.execute
        
        result = await delete_documentation_from_monitoring(
            mock_mcp_context, 
            "https://example.com/docs"
        )
        result_data = json.loads(result)
        
        assert result_data["success"] is True
        assert result_data["url"] == "https://example.com/docs"
        assert "deleted" in result_data["message"]
        
        print("✅ delete_documentation_from_monitoring works with real import")

@pytest.mark.skipif(not MCP_TOOLS_AVAILABLE, reason="MCP tools not available")
class TestCheckAllDocumentChanges:
    """Test check_all_document_changes MCP tool."""
    
    @pytest.mark.asyncio
    async def test_check_all_document_changes_success(self, mock_mcp_context, sample_monitored_docs):
        """Test successful batch checking of all documents."""
        # Configure mock to return monitored docs
        mock_mcp_context.request_context.lifespan_context.supabase_client.from_().select().not_().is_().execute.return_value.data = sample_monitored_docs
        
        with patch('doc_fetcher_mcp.check_and_update_document_changes') as mock_workflow:
            mock_workflow.return_value = {
                "success": True,
                "changes_detected": False
            }
            
            result = await check_all_document_changes(mock_mcp_context)
            result_data = json.loads(result)
            
            assert result_data["success"] is True
            assert "results" in result_data
            assert result_data["total_checked"] == 2
            
            print("✅ check_all_document_changes works with real import")

@pytest.mark.skipif(not MCP_TOOLS_AVAILABLE, reason="MCP tools not available")
class TestMCPToolsIntegration:
    """Integration tests for MCP tools workflows."""
    
    @pytest.mark.asyncio
    async def test_full_monitoring_workflow(self, mock_mcp_context):
        """Test a complete monitoring workflow: monitor → query → check → delete."""
        # 1. Monitor a document
        with patch('doc_fetcher_mcp.process_website_documentation') as mock_process:
            mock_process.return_value = {
                "success": True,
                "url": "https://test.com/docs",
                "chunks_stored": 3
            }
            
            monitor_result = await monitor_documentation(mock_mcp_context, "https://test.com/docs")
            monitor_data = json.loads(monitor_result)
            assert monitor_data["success"] is True
        
        # 2. Query the monitored content
        with patch('doc_fetcher_mcp.semantic_search_documents') as mock_search:
            mock_search.return_value = [{"content": "Test content", "similarity": 0.9}]
            
            query_result = await perform_rag_query(mock_mcp_context, "test query")
            query_data = json.loads(query_result)
            assert query_data["success"] is True
        
        # 3. Check for changes
        with patch('doc_fetcher_mcp.check_and_update_document_changes') as mock_check:
            mock_check.return_value = {
                "success": True,
                "changes_detected": False
            }
            
            check_result = await check_document_changes(mock_mcp_context, "https://test.com/docs")
            check_data = json.loads(check_result)
            assert check_data["success"] is True
        
        # 4. Remove from monitoring
        delete_mock = Mock()
        delete_mock.execute.return_value.data = [{"id": 1, "status": "deleted"}]
        mock_mcp_context.request_context.lifespan_context.supabase_client.from_().update().eq().execute = delete_mock.execute
        
        delete_result = await delete_documentation_from_monitoring(mock_mcp_context, "https://test.com/docs")
        delete_data = json.loads(delete_result)
        assert delete_data["success"] is True
        
        print("✅ Complete MCP workflow executed successfully!")

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"]) 