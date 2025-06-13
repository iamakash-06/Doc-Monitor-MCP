# Makefile for Doc-Monitor-MCP
# ============================
# 
# This Makefile provides easy commands for setting up, testing, and managing
# your Doc-Monitor-MCP installation.
#
# Quick Start:
#   make setup     - Complete setup wizard
#   make validate  - Validate configuration
#   make dev       - Start development server
#   make help      - Show all available commands

.PHONY: setup validate health-check db-setup dev test clean help
.PHONY: test-deps test-framework test-conceptual test-performance test-functionality test-direct test-all test-verbose test-help

# ================================
# SETUP & CONFIGURATION COMMANDS
# ================================

# Complete setup wizard (recommended for first-time setup)
setup:
	@echo "🚀 Starting Doc-Monitor-MCP setup wizard..."
	python scripts/setup.py

# Automated setup (non-interactive)
setup-auto:
	@echo "🤖 Running automated setup..."
	python scripts/setup.py --auto

# Validate environment and configuration
validate:
	@echo "🔍 Validating environment configuration..."
	python scripts/validate_env.py

# Quick validation (skip connection tests)
validate-quick:
	@echo "⚡ Running quick validation..."
	python scripts/validate_env.py --no-connections

# Comprehensive health check
health-check:
	@echo "🏥 Running health check..."
	python scripts/health_check.py

# Full health check with performance tests
health-check-full:
	@echo "🏥 Running comprehensive health check..."
	python scripts/health_check.py --full

# Setup database schema only
db-setup:
	@echo "🛠️ Setting up database schema..."
	python scripts/db_setup.py

# Reset database schema (WARNING: destroys data)
db-reset:
	@echo "⚠️ Resetting database schema..."
	@read -p "This will destroy all data. Continue? (y/N) " confirm && \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		python scripts/db_setup.py --reset; \
	else \
		echo "Database reset cancelled."; \
	fi

# Validate database schema only
db-validate:
	@echo "🔍 Validating database schema..."
	python scripts/db_setup.py --validate-only

# ================================
# DEVELOPMENT COMMANDS
# ================================

# Start development server
dev:
	@echo "🚀 Starting Doc-Monitor-MCP server..."
	uv run src/doc_fetcher_mcp.py

# Start server with debug logging
dev-debug:
	@echo "🐛 Starting server in debug mode..."
	DEBUG=true uv run src/doc_fetcher_mcp.py

# Install dependencies
install:
	@echo "📦 Installing dependencies..."
	uv pip install -e .
	@echo "🔧 Setting up Crawl4AI..."
	crawl4ai-setup

# Update dependencies
update:
	@echo "🔄 Updating dependencies..."
	uv pip install --upgrade -e .

# ================================
# TESTING COMMANDS
# ================================

# Default target - run complete setup validation
default: validate

# Install test dependencies
test-deps:
	@echo "🔧 Installing test dependencies..."
	uv add --dev pytest pytest-asyncio pytest-mock pytest-cov pytest-xdist coverage

# Run all tests
test: test-deps test-all

# Original testing commands (maintained for compatibility)
test-framework: test-deps
	@echo "🏗️ Running test framework validation..."
	python tests/test_runner.py --type framework

# Test MCP conceptual validation
test-conceptual: test-deps  
	@echo "🎯 Running MCP conceptual validation..."
	python tests/test_runner.py --type conceptual

# Test performance
test-performance: test-deps
	@echo "⚡ Running performance tests..."
	python tests/test_runner.py --type performance

# Test functionality
test-functionality: test-deps
	@echo "🧪 Running functionality tests..."
	python tests/test_runner.py --type functionality

# Test direct MCP tool imports and functionality
test-direct: test-deps
	@echo "🎯 Running direct MCP tool tests..."
	python tests/test_runner.py --type direct

# Run all working tests
test-all: test-deps
	@echo "🚀 Running all MCP tool tests..."
	python tests/test_runner.py --type all

# Run with verbose output
test-verbose: test-deps
	@echo "📝 Running tests with verbose output..."
	pytest tests/test_mcp_functionality.py -v -s

# Run a quick test
test-quick:
	@echo "⚡ Running quick test..."
	pytest tests/test_mcp_functionality.py::TestMCPFramework::test_testing_environment -v

# Show test help
test-help:
	@echo "🔧 MCP Tools Test Commands:"
	@echo "  make test           - Run all tests (default)"
	@echo "  make test-framework - Test the framework itself"
	@echo "  make test-conceptual- Test MCP conceptual validation" 
	@echo "  make test-performance- Test performance characteristics"
	@echo "  make test-functionality- Test functionality"
	@echo "  make test-direct    - Test direct MCP tool imports & functions"
	@echo "  make test-all       - Run all working tests"
	@echo "  make test-verbose   - Run with verbose output"
	@echo "  make test-quick     - Run a quick test"
	@echo "  make test-help      - Show this help"
	@echo "  make clean          - Clean test artifacts"
	@echo ""
	@echo "📋 Direct pytest commands:"
	@echo "  pytest tests/test_mcp_functionality.py -v"
	@echo "  pytest tests/test_mcp_tools_direct.py -v"
	@echo "  python tests/test_runner.py --type all"

# ================================
# MAINTENANCE COMMANDS
# ================================

# Clean all artifacts and temporary files
clean:
	@echo "🧹 Cleaning artifacts and temporary files..."
	rm -rf tests/.pytest_cache
	rm -rf tests/__pycache__
	rm -rf tests/htmlcov
	rm -f tests/coverage.json
	rm -f tests/mcp_test_report.txt
	rm -f tests/mcp_comprehensive_test_report.txt
	rm -rf .pytest_cache
	rm -rf .venv/__pycache__ 2>/dev/null || true
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# Clean and reset everything (including .env)
clean-all: clean
	@echo "🔄 Resetting to fresh state..."
	@read -p "This will remove .env file. Continue? (y/N) " confirm && \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		rm -f .env; \
		echo "Project reset to fresh state. Run 'make setup' to reconfigure."; \
	else \
		echo "Clean-all cancelled."; \
	fi

# ================================
# HELP & DOCUMENTATION
# ================================

# Show comprehensive help
help:
	@echo ""
	@echo "📋 Doc-Monitor-MCP - Available Commands"
	@echo "======================================"
	@echo ""
	@echo "🚀 GETTING STARTED:"
	@echo "  make setup          Complete setup wizard (first time)"
	@echo "  make setup-auto     Automated setup (non-interactive)"
	@echo "  make validate       Validate configuration"
	@echo "  make dev            Start development server"
	@echo ""
	@echo "🔧 SETUP & CONFIGURATION:"
	@echo "  make setup          Interactive setup wizard"
	@echo "  make setup-auto     Automated setup with defaults"
	@echo "  make validate       Full environment validation"
	@echo "  make validate-quick Quick validation (no API tests)"
	@echo "  make db-setup       Setup database schema only"
	@echo "  make db-validate    Validate database schema"
	@echo "  make db-reset       Reset database (destroys data)"
	@echo ""
	@echo "🏥 HEALTH & DIAGNOSTICS:"
	@echo "  make health-check      Basic health check"
	@echo "  make health-check-full Comprehensive diagnostics"
	@echo ""
	@echo "🛠️ DEVELOPMENT:"
	@echo "  make dev            Start MCP server"
	@echo "  make dev-debug      Start server with debug logging"
	@echo "  make install        Install dependencies"
	@echo "  make update         Update dependencies"
	@echo ""
	@echo "🧪 TESTING:"
	@echo "  make test           Run all tests"
	@echo "  make test-quick     Run quick test"
	@echo "  make test-framework Test framework validation"
	@echo "  make test-help      Show detailed test help"
	@echo ""
	@echo "🧹 MAINTENANCE:"
	@echo "  make clean          Clean temporary files"
	@echo "  make clean-all      Reset to fresh state"
	@echo "  make help           Show this help"
	@echo ""
	@echo "📚 QUICK TIPS:"
	@echo "  • First time? Run: make setup"
	@echo "  • Having issues? Run: make validate"
	@echo "  • Need diagnostics? Run: make health-check-full"
	@echo "  • Start developing: make dev"
	@echo "" 

# Database Migration (Flyway)
.PHONY: db-migrate db-info db-setup-flyway

db-migrate: ## Run database migrations
	@echo "🚀 Running database migrations..."
	@./db/scripts/migrate.sh

db-info: ## Show migration status
	@echo "📊 Showing migration status..."
	@./db/scripts/info.sh

db-setup-flyway: ## Set up database using Flyway (replaces manual setup)
	@echo "🛠️ Setting up database with Flyway..."
	@./db/scripts/migrate.sh
	@echo "✅ Database setup completed with Flyway!"
