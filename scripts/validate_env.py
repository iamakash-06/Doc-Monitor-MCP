#!/usr/bin/env python3
"""
Environment Validation Script for Doc-Monitor-MCP
=================================================

This script validates all environment variables and tests API connections
to ensure the system is properly configured before running.

Usage:
    python scripts/validate_env.py
    python scripts/validate_env.py --fix  # Interactive mode to fix issues
"""

import os
import sys
import asyncio
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import json

# Add src to path to import our modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

@dataclass
class ValidationResult:
    """Result of a validation check."""
    component: str
    status: str  # 'pass', 'fail', 'warning'
    message: str
    details: Optional[str] = None

class EnvironmentValidator:
    """Validates environment configuration and API connections."""
    
    def __init__(self):
        self.results: List[ValidationResult] = []
        self.project_root = Path(__file__).parent.parent
        self.env_file = self.project_root / ".env"
        self.env_template = self.project_root / "env.template"
        
    def load_environment(self) -> Dict[str, str]:
        """Load environment variables from .env file."""
        env_vars = {}
        
        if not self.env_file.exists():
            self.add_result("Environment File", "fail", 
                          f"No .env file found at {self.env_file}")
            return env_vars
            
        try:
            with open(self.env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        env_vars[key.strip()] = value.strip()
        except Exception as e:
            self.add_result("Environment File", "fail", 
                          f"Error reading .env file: {e}")
            
        return env_vars
    
    def add_result(self, component: str, status: str, message: str, details: str = None):
        """Add a validation result."""
        self.results.append(ValidationResult(component, status, message, details))
    
    def validate_required_vars(self, env_vars: Dict[str, str]) -> None:
        """Validate required environment variables."""
        required_vars = {
            'OPENAI_API_KEY': 'OpenAI API key for embeddings',
            'SUPABASE_URL': 'Supabase project URL',
            'SUPABASE_SERVICE_KEY': 'Supabase service role key'
        }
        
        for var, description in required_vars.items():
            if var not in env_vars or not env_vars[var] or env_vars[var] == f"your_{var.lower()}_here":
                self.add_result(f"Required Variable: {var}", "fail",
                              f"Missing or invalid {description}")
            else:
                self.add_result(f"Required Variable: {var}", "pass",
                              f"{description} is set")
    
    def validate_optional_vars(self, env_vars: Dict[str, str]) -> None:
        """Validate optional environment variables with defaults."""
        optional_vars = {
            'HOST': '0.0.0.0',
            'PORT': '8051',
            'TRANSPORT': 'sse',
            'MODEL_CHOICE': 'gpt-4o-mini',
            'MAX_CONCURRENT': '10',
            'MAX_DEPTH': '3',
            'CHUNK_SIZE': '5000'
        }
        
        for var, default in optional_vars.items():
            if var not in env_vars:
                self.add_result(f"Optional Variable: {var}", "warning",
                              f"Using default value: {default}")
            else:
                self.add_result(f"Optional Variable: {var}", "pass",
                              f"Set to: {env_vars[var]}")
    
    async def test_openai_connection(self, api_key: str) -> None:
        """Test OpenAI API connection."""
        if not api_key or api_key == "your_openai_api_key_here":
            self.add_result("OpenAI Connection", "fail", "Invalid API key")
            return
            
        try:
            import openai
            client = openai.OpenAI(api_key=api_key)
            
            # Test with a simple embedding request
            response = client.embeddings.create(
                model="text-embedding-3-small",
                input="test connection"
            )
            
            if response.data:
                self.add_result("OpenAI Connection", "pass", 
                              "Successfully connected to OpenAI API")
            else:
                self.add_result("OpenAI Connection", "fail", 
                              "OpenAI API returned empty response")
                
        except ImportError:
            self.add_result("OpenAI Connection", "fail", 
                          "OpenAI package not installed")
        except Exception as e:
            error_msg = str(e)
            if "api_key" in error_msg.lower():
                self.add_result("OpenAI Connection", "fail", 
                              "Invalid OpenAI API key")
            elif "quota" in error_msg.lower():
                self.add_result("OpenAI Connection", "fail", 
                              "OpenAI API quota exceeded")
            else:
                self.add_result("OpenAI Connection", "fail", 
                              f"OpenAI API error: {error_msg}")
    
    async def test_supabase_connection(self, url: str, key: str) -> None:
        """Test Supabase connection."""
        if not url or url == "your_supabase_project_url_here":
            self.add_result("Supabase Connection", "fail", "Invalid Supabase URL")
            return
            
        if not key or key == "your_supabase_service_key_here":
            self.add_result("Supabase Connection", "fail", "Invalid Supabase service key")
            return
            
        try:
            from supabase import create_client
            client = create_client(url, key)
            
            # Test connection by trying to access tables
            response = client.table("crawled_pages").select("count", count="exact").limit(1).execute()
            
            self.add_result("Supabase Connection", "pass", 
                          "Successfully connected to Supabase")
            
        except ImportError:
            self.add_result("Supabase Connection", "fail", 
                          "Supabase package not installed")
        except Exception as e:
            error_msg = str(e)
            if "Invalid API key" in error_msg or "authentication" in error_msg.lower():
                self.add_result("Supabase Connection", "fail", 
                              "Invalid Supabase credentials")
            elif "relation" in error_msg.lower() and "does not exist" in error_msg.lower():
                self.add_result("Supabase Schema", "warning", 
                              "Database schema not set up. Run 'make db-setup'")
            else:
                self.add_result("Supabase Connection", "fail", 
                              f"Supabase error: {error_msg}")
    
    def validate_file_structure(self) -> None:
        """Validate required files and directories exist."""
        required_files = [
            ("crawled_pages.sql", "Database schema file"),
            ("src/doc_fetcher_mcp.py", "Main MCP server file"),
            ("pyproject.toml", "Project configuration"),
        ]
        
        for file_path, description in required_files:
            full_path = self.project_root / file_path
            if full_path.exists():
                self.add_result(f"File: {file_path}", "pass", f"{description} found")
            else:
                self.add_result(f"File: {file_path}", "fail", f"Missing {description}")
    
    def check_dependencies(self) -> None:
        """Check if required Python packages are installed."""
        required_packages = [
            "crawl4ai",
            "mcp", 
            "supabase",
            "openai",
            "dotenv"
        ]
        
        for package in required_packages:
            try:
                __import__(package)
                self.add_result(f"Package: {package}", "pass", f"{package} is installed")
            except ImportError:
                self.add_result(f"Package: {package}", "fail", 
                              f"{package} not installed. Run 'uv pip install -e .'")
    
    async def run_validation(self, test_connections: bool = True) -> bool:
        """Run complete validation."""
        print("🔍 Doc-Monitor-MCP Environment Validation")
        print("=" * 50)
        
        # Load environment
        env_vars = self.load_environment()
        
        # File structure validation
        self.validate_file_structure()
        
        # Dependencies validation
        self.check_dependencies()
        
        # Environment variables validation
        self.validate_required_vars(env_vars)
        self.validate_optional_vars(env_vars)
        
        # API connections validation (if requested)
        if test_connections:
            print("\n🌐 Testing API connections...")
            await self.test_openai_connection(env_vars.get('OPENAI_API_KEY', ''))
            await self.test_supabase_connection(
                env_vars.get('SUPABASE_URL', ''),
                env_vars.get('SUPABASE_SERVICE_KEY', '')
            )
        
        # Display results
        self.display_results()
        
        # Return overall status
        has_failures = any(r.status == "fail" for r in self.results)
        return not has_failures
    
    def display_results(self) -> None:
        """Display validation results in a formatted way."""
        print("\n" + "=" * 50)
        print("📋 VALIDATION RESULTS")
        print("=" * 50)
        
        # Group results by status
        passed = [r for r in self.results if r.status == "pass"]
        warnings = [r for r in self.results if r.status == "warning"]
        failed = [r for r in self.results if r.status == "fail"]
        
        # Display passed checks
        if passed:
            print(f"\n✅ PASSED ({len(passed)} checks)")
            for result in passed:
                print(f"   ✓ {result.component}: {result.message}")
        
        # Display warnings
        if warnings:
            print(f"\n⚠️  WARNINGS ({len(warnings)} checks)")
            for result in warnings:
                print(f"   ⚠ {result.component}: {result.message}")
        
        # Display failures
        if failed:
            print(f"\n❌ FAILED ({len(failed)} checks)")
            for result in failed:
                print(f"   ✗ {result.component}: {result.message}")
                if result.details:
                    print(f"     Details: {result.details}")
        
        # Summary
        total = len(self.results)
        print(f"\n📊 SUMMARY: {len(passed)} passed, {len(warnings)} warnings, {len(failed)} failed")
        
        if failed:
            print("\n🔧 TO FIX ISSUES:")
            print("   1. Copy env.template to .env: cp env.template .env")
            print("   2. Edit .env with your actual API keys")
            print("   3. Run database setup: make db-setup")
            print("   4. Install dependencies: uv pip install -e .")
        else:
            print("\n🎉 All checks passed! Your environment is ready.")

def main():
    """Main validation function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Validate Doc-Monitor-MCP environment")
    parser.add_argument("--no-connections", action="store_true", 
                       help="Skip API connection tests")
    parser.add_argument("--json", action="store_true",
                       help="Output results as JSON")
    
    args = parser.parse_args()
    
    validator = EnvironmentValidator()
    
    # Run validation
    success = asyncio.run(validator.run_validation(test_connections=not args.no_connections))
    
    # JSON output
    if args.json:
        results_dict = {
            "success": success,
            "results": [
                {
                    "component": r.component,
                    "status": r.status,
                    "message": r.message,
                    "details": r.details
                }
                for r in validator.results
            ]
        }
        print(json.dumps(results_dict, indent=2))
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main() 