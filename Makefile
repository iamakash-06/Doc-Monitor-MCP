# Makefile for MCP Tools Test Suite
# ================================

.PHONY: test test-deps test-framework test-conceptual test-performance test-functionality test-direct test-all test-verbose test-help clean

# Default target
test: test-deps test-all

# Install test dependencies
test-deps:
	@echo "🔧 Installing test dependencies..."
	uv add --dev pytest pytest-asyncio pytest-mock pytest-cov pytest-xdist coverage

# Test the framework itself
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

# Clean test artifacts
clean:
	@echo "🧹 Cleaning test artifacts..."
	rm -rf tests/.pytest_cache
	rm -rf tests/__pycache__
	rm -rf tests/htmlcov
	rm -f tests/coverage.json
	rm -f tests/mcp_test_report.txt
	rm -f tests/mcp_comprehensive_test_report.txt
	rm -rf .pytest_cache
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true 