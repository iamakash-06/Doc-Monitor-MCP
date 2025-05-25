# 🌟 Doc Monitor MCP - Repository Branches

This repository contains the **Doc Monitor MCP** project with clean branch organization for different feature sets.

## 📂 Branch Structure

### 🏠 `main` - Production Doc Monitor
**Clean, stable doc-monitor implementation**

This branch contains the core documentation monitoring functionality:
- 📖 **Documentation Monitoring**: Track changes in web documentation
- 🔍 **Change Detection**: Automatically detect content modifications
- 🧠 **RAG Capabilities**: Semantic search across monitored documentation
- 📊 **Version Tracking**: Complete history of documentation changes
- 🌐 **Multi-Format Support**: Web pages, sitemaps, OpenAPI specs
- 🔧 **MCP Integration**: Standards-compliant Model Context Protocol server

**Key Files:**
- `src/doc_fetcher_mcp.py` - Main MCP server
- `src/utils.py` - Core utilities
- `crawled_pages.sql` - Database schema
- `README.md` - Complete documentation

**Usage:**
```bash
# Install dependencies
uv pip install -e .

# Setup database (apply crawled_pages.sql in Supabase)

# Run the server
uv run src/doc_fetcher_mcp.py
```

---

### 🤖 `feature/automated-code-agent` - AI-Powered Code Automation
**Advanced automation layer on top of doc-monitor**

This branch extends doc-monitor with intelligent code change automation:

#### ✨ **Additional Capabilities**
- 🧠 **AI-Powered Analysis**: LLM analysis of documentation changes
- ⚡ **Automatic Code Generation**: Generate code changes based on doc updates
- 👤 **Human Approval Workflow**: Safe application with human oversight
- 💾 **Automatic Backups**: File backups before any modifications
- 📊 **Confidence Scoring**: AI confidence ratings for proposed changes
- 🔒 **Safety Controls**: Multi-layer protection and validation

#### 📁 **Additional Files**
- `src/code_change_agent.py` - Main automation agent
- `code_change_schema.sql` - Extended database schema
- `start_code_change_agent.py` - Integrated startup script
- `setup_code_agent.py` - Dependency installation
- `test_integration.py` - System validation
- `example_usage.py` - Complete workflow demo
- `AUTOMATED_CODE_AGENT_SUMMARY.md` - Implementation guide

#### 🚀 **Usage**
```bash
# Switch to feature branch
git checkout feature/automated-code-agent

# Setup the enhanced system
python3 setup_code_agent.py

# Apply extended schema (code_change_schema.sql in Supabase)

# Start integrated system
python3 start_code_change_agent.py

# Test the system
python3 example_usage.py
```

#### 🛠️ **Workflow**
1. **Monitor** documentation with existing doc-monitor
2. **Detect** changes automatically
3. **Analyze** impact using AI
4. **Generate** specific code changes
5. **Review** and approve changes
6. **Apply** safely with backups

---

## 🔄 Branch Workflow

### For Doc Monitor Only
```bash
git checkout main
# Use standard doc-monitor functionality
```

### For Automated Code Changes
```bash
git checkout feature/automated-code-agent
# Use enhanced AI-powered automation
```

### Development
```bash
# Feature development
git checkout feature/automated-code-agent
# Make changes
git add .
git commit -m "feat: your feature"

# Keep main clean
git checkout main
# Only merge stable, tested features
```

## 🎯 Which Branch Should You Use?

### Choose `main` if you want:
- ✅ **Stable, production-ready** doc monitoring
- ✅ **Simple setup** and operation
- ✅ **Core functionality** only
- ✅ **No AI dependencies** beyond embeddings

### Choose `feature/automated-code-agent` if you want:
- 🚀 **Cutting-edge automation** capabilities
- 🤖 **AI-powered code generation**
- 🔧 **Advanced workflow integration**
- 📈 **Maximum productivity gains**

## 📞 Support

- **Issues**: Use GitHub Issues for both branches
- **Documentation**: See README.md in each branch
- **Examples**: Check example files in the automated-code-agent branch

---

**Current Branch:** `main` - Clean doc-monitor implementation
**Enhanced Branch:** `feature/automated-code-agent` - AI-powered automation 