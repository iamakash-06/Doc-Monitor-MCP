<h1 align="center">Doc Monitor MCP</h1>

**Advanced Documentation Monitoring & RAG Server for AI Agents**

---

`doc-monitor` is an intelligent Model Context Protocol (MCP) server that continuously monitors documentation, detects changes, and provides advanced Retrieval Augmented Generation (RAG) capabilities for AI agents and coding assistants. It automatically crawls web documentation, tracks versions, analyzes change impact, and maintains a searchable knowledge base to help developers stay current with evolving APIs and documentation.

## 🚀 Key Features

- **🔍 Smart Documentation Monitoring**: Continuously track documentation changes and analyze their impact
- **📊 Version Control**: Automatic versioning of documentation with detailed change tracking 
- **🧠 Impact Analysis**: AI-powered analysis of breaking changes and API modifications
- **🌐 Multi-Format Support**: Handle web pages, sitemaps, OpenAPI specs, and text files
- **⚡ High-Performance Crawling**: Parallel processing with memory-adaptive dispatching
- **🎯 Semantic Search**: Vector-based RAG queries with advanced filtering
- **🔧 MCP Integration**: Standards-compliant Model Context Protocol server
- **🐳 Production Ready**: Docker support with comprehensive database schema

## 🏗️ Architecture

**Core Technologies:**
- **Python 3.12+** with asyncio for high-performance concurrent operations
- **Crawl4AI** for intelligent web crawling and content extraction  
- **Supabase** with pgvector for vector storage and semantic search
- **OpenAI Embeddings** (text-embedding-3-small) for content vectorization
- **FastMCP** for Model Context Protocol server implementation

**Database Schema:**
- `crawled_pages`: Document chunks with version tracking and vector embeddings
- `document_changes`: Detailed change history with impact analysis
- `monitored_documentations`: Active monitoring configuration and metadata

## 📦 Installation

### Docker (Recommended)

```bash
git clone https://github.com/iamakash-06/doc-monitor.git
cd doc-monitor
docker build -t doc-monitor .
```

### Local Development

```bash
git clone https://github.com/iamakash-06/doc-monitor.git
cd doc-monitor
pip install uv
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e .
```

## ⚙️ Configuration

Create a `.env` file in the project root:

```env
# Server Configuration
HOST=0.0.0.0
PORT=8051
TRANSPORT=sse

# OpenAI API
OPENAI_API_KEY=your_openai_api_key

# Supabase Database
SUPABASE_URL=your_supabase_project_url
SUPABASE_SERVICE_KEY=your_supabase_service_key

# Optional: Contextual Embeddings (requires additional OpenAI model access)
MODEL_CHOICE=gpt-4o-mini
```

## 🗄️ Database Setup

1. Create a new Supabase project at [supabase.com](https://supabase.com)
2. Navigate to the SQL Editor in your dashboard
3. Execute the complete SQL schema from `crawled_pages.sql`:

```bash
# Copy the entire contents of crawled_pages.sql and run in Supabase SQL Editor
```

This creates the required tables, indexes, functions, and RLS policies.

## ▶️ Running the Server

### Docker

```bash
docker run --env-file .env -p 8051:8051 doc-monitor
```

### Local

```bash
uv run src/doc_fetcher_mcp.py
```

The server will start and be available at `http://localhost:8051` (SSE) or via stdio transport.

## 🛠️ MCP Tools API Reference

### Documentation Monitoring

#### `monitor_documentation`
Start monitoring a documentation URL with automatic change detection.

```json
{
  "name": "monitor_documentation",
  "arguments": {
    "url": "https://api.example.com/docs",
    "notes": "Critical API documentation - monitor for breaking changes"
  }
}
```

**Supported URL Types:**
- Regular web pages (with recursive internal link crawling)
- Sitemaps (XML format)
- OpenAPI specifications (JSON/YAML)
- Text/Markdown files

#### `check_document_changes`
Check a specific URL for changes and update the knowledge base.

```json
{
  "name": "check_document_changes", 
  "arguments": {
    "url": "https://api.example.com/docs"
  }
}
```

#### `check_all_document_changes`
Scan all monitored documentation for changes.

```json
{
  "name": "check_all_document_changes",
  "arguments": {}
}
```

### Search & Retrieval

#### `perform_rag_query`
Semantic search across all documentation with optional filtering.

```json
{
  "name": "perform_rag_query",
  "arguments": {
    "query": "How to authenticate API requests",
    "source": "api.example.com",
    "match_count": 10,
    "endpoint": "/auth",
    "method": "POST"
  }
}
```

### Management & Analytics

#### `list_monitored_documentations`
Get all actively monitored documentation sources.

#### `get_available_sources`
List all unique domains/sources in the knowledge base.

#### `get_document_history`
View complete change history for a specific URL.

#### `delete_documentation_from_monitoring`
Remove a URL from active monitoring.

## 🔌 Integration Examples

### Claude Desktop (SSE Transport)

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "doc-monitor": {
      "transport": "sse",
      "url": "http://localhost:8051/sse"
    }
  }
}
```

### Stdio Transport

```json
{
  "mcpServers": {
    "doc-monitor": {
      "command": "uv",
      "args": ["run", "src/doc_fetcher_mcp.py"],
      "env": {
        "TRANSPORT": "stdio",
        "OPENAI_API_KEY": "your_openai_api_key", 
        "SUPABASE_URL": "your_supabase_url",
        "SUPABASE_SERVICE_KEY": "your_supabase_service_key"
      }
    }
  }
}
```

## 🎯 Use Cases

### API Documentation Monitoring
```bash
# Monitor critical API documentation
monitor_documentation("https://api.stripe.com/docs")

# Check for breaking changes
check_document_changes("https://api.stripe.com/docs") 

# Search for specific functionality
perform_rag_query("payment methods", source="api.stripe.com")
```

### Documentation Change Analysis
The system automatically:
- 🔍 **Detects Changes**: Content additions, modifications, and deletions
- 📈 **Analyzes Impact**: Identifies breaking changes and API modifications  
- 🚨 **Provides Recommendations**: Actionable insights for maintaining compatibility
- 📋 **Tracks History**: Complete audit trail of all documentation evolution

## 🔧 Advanced Configuration

### Memory and Performance

The server includes adaptive memory management:

```python
CHUNK_SIZE = 5000          # Token limit per chunk
MAX_CONCURRENT = 10        # Parallel crawling limit  
MAX_DEPTH = 3             # Recursive crawling depth
MEMORY_THRESHOLD_PERCENT = 70.0  # Memory usage limit
```

### Contextual Embeddings

Enable enhanced retrieval with contextual embeddings by setting `MODEL_CHOICE`:

```env
MODEL_CHOICE= text-embedding-3-large # Enables context-aware chunk processing
```



## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## 🆘 Support

- **Issues**: [GitHub Issues](https://github.com/iamakash-06/doc-monitor/issues)
- **Discussions**: [GitHub Discussions](https://github.com/iamakash-06/doc-monitor/discussions)

---

**doc-monitor** — Intelligent documentation monitoring and RAG for the AI-powered development workflow.