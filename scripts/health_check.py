#!/usr/bin/env python3
"""
Health Check Script for Doc-Monitor-MCP
======================================

This script performs comprehensive health checks on the system including:
- System resources (memory, disk space)
- Database schema validation
- Service connectivity
- Performance benchmarks

Usage:
    python scripts/health_check.py
    python scripts/health_check.py --full  # Run extended diagnostics
"""

import os
import sys
import asyncio
import psutil
import time
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
import json

# Add src to path to import our modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

@dataclass
class HealthResult:
    """Result of a health check."""
    component: str
    status: str  # 'healthy', 'warning', 'critical'
    message: str
    metrics: Optional[Dict] = None

class HealthChecker:
    """Comprehensive health checker for Doc-Monitor-MCP."""
    
    def __init__(self):
        self.results: List[HealthResult] = []
        self.project_root = Path(__file__).parent.parent
        
    def add_result(self, component: str, status: str, message: str, metrics: Dict = None):
        """Add a health check result."""
        self.results.append(HealthResult(component, status, message, metrics))
    
    def check_system_resources(self) -> None:
        """Check system resources like memory, disk space, CPU."""
        try:
            # Memory check
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            if memory_percent < 70:
                status = "healthy"
                message = f"Memory usage: {memory_percent:.1f}%"
            elif memory_percent < 85:
                status = "warning"
                message = f"High memory usage: {memory_percent:.1f}%"
            else:
                status = "critical"
                message = f"Critical memory usage: {memory_percent:.1f}%"
            
            self.add_result("System Memory", status, message, {
                "total_gb": round(memory.total / (1024**3), 1),
                "available_gb": round(memory.available / (1024**3), 1),
                "percent_used": memory_percent
            })
            
            # Disk space check
            disk = psutil.disk_usage(str(self.project_root))
            disk_percent = (disk.used / disk.total) * 100
            
            if disk_percent < 80:
                status = "healthy"
                message = f"Disk usage: {disk_percent:.1f}%"
            elif disk_percent < 90:
                status = "warning"
                message = f"High disk usage: {disk_percent:.1f}%"
            else:
                status = "critical"
                message = f"Critical disk usage: {disk_percent:.1f}%"
            
            self.add_result("Disk Space", status, message, {
                "total_gb": round(disk.total / (1024**3), 1),
                "free_gb": round(disk.free / (1024**3), 1),
                "percent_used": disk_percent
            })
            
            # CPU check
            cpu_percent = psutil.cpu_percent(interval=1)
            
            if cpu_percent < 70:
                status = "healthy"
                message = f"CPU usage: {cpu_percent:.1f}%"
            elif cpu_percent < 90:
                status = "warning"
                message = f"High CPU usage: {cpu_percent:.1f}%"
            else:
                status = "critical"
                message = f"Critical CPU usage: {cpu_percent:.1f}%"
            
            self.add_result("CPU Usage", status, message, {
                "percent_used": cpu_percent,
                "cpu_count": psutil.cpu_count()
            })
            
        except Exception as e:
            self.add_result("System Resources", "critical", f"Error checking resources: {e}")
    
    async def check_database_schema(self) -> None:
        """Check database schema and required tables."""
        try:
            # Load environment for database connection
            env_vars = self._load_env_vars()
            
            if not env_vars.get('SUPABASE_URL') or not env_vars.get('SUPABASE_SERVICE_KEY'):
                self.add_result("Database Schema", "critical", "Missing database credentials")
                return
            
            from supabase import create_client
            client = create_client(env_vars['SUPABASE_URL'], env_vars['SUPABASE_SERVICE_KEY'])
            
            # Check required tables
            required_tables = ['crawled_pages', 'document_changes', 'monitored_documentations']
            table_status = {}
            
            for table in required_tables:
                try:
                    response = client.table(table).select("count", count="exact").limit(1).execute()
                    table_status[table] = "exists"
                except Exception as e:
                    if "does not exist" in str(e):
                        table_status[table] = "missing"
                    else:
                        table_status[table] = "error"
            
            missing_tables = [t for t, status in table_status.items() if status == "missing"]
            error_tables = [t for t, status in table_status.items() if status == "error"]
            
            if missing_tables:
                self.add_result("Database Schema", "critical", 
                              f"Missing tables: {', '.join(missing_tables)}")
            elif error_tables:
                self.add_result("Database Schema", "warning",
                              f"Table access errors: {', '.join(error_tables)}")
            else:
                self.add_result("Database Schema", "healthy", "All required tables exist")
            
            # Check for pgvector extension
            try:
                response = client.rpc("version").execute()
                # Try a vector operation to verify pgvector is available
                test_query = client.table("crawled_pages").select("embedding").limit(1).execute()
                self.add_result("Vector Extension", "healthy", "pgvector extension is available")
            except Exception as e:
                if "vector" in str(e).lower():
                    self.add_result("Vector Extension", "critical", "pgvector extension not enabled")
                else:
                    self.add_result("Vector Extension", "warning", f"Could not verify pgvector: {e}")
                    
        except ImportError:
            self.add_result("Database Schema", "critical", "Supabase package not installed")
        except Exception as e:
            self.add_result("Database Schema", "critical", f"Database connection error: {e}")
    
    async def check_service_performance(self) -> None:
        """Check performance of key services."""
        try:
            env_vars = self._load_env_vars()
            
            # Test OpenAI API performance
            if env_vars.get('OPENAI_API_KEY'):
                start_time = time.time()
                try:
                    import openai
                    client = openai.OpenAI(api_key=env_vars['OPENAI_API_KEY'])
                    
                    response = client.embeddings.create(
                        model="text-embedding-3-small",
                        input="performance test"
                    )
                    
                    latency = time.time() - start_time
                    
                    if latency < 2.0:
                        status = "healthy"
                        message = f"OpenAI API latency: {latency:.2f}s"
                    elif latency < 5.0:
                        status = "warning"
                        message = f"Slow OpenAI API: {latency:.2f}s"
                    else:
                        status = "critical"
                        message = f"Very slow OpenAI API: {latency:.2f}s"
                    
                    self.add_result("OpenAI Performance", status, message, {
                        "latency_seconds": latency,
                        "model": "text-embedding-3-small"
                    })
                    
                except Exception as e:
                    self.add_result("OpenAI Performance", "critical", f"API error: {e}")
            
            # Test Supabase performance  
            if env_vars.get('SUPABASE_URL') and env_vars.get('SUPABASE_SERVICE_KEY'):
                start_time = time.time()
                try:
                    from supabase import create_client
                    client = create_client(env_vars['SUPABASE_URL'], env_vars['SUPABASE_SERVICE_KEY'])
                    
                    response = client.table("crawled_pages").select("id").limit(1).execute()
                    
                    latency = time.time() - start_time
                    
                    if latency < 1.0:
                        status = "healthy"
                        message = f"Supabase latency: {latency:.2f}s"
                    elif latency < 3.0:
                        status = "warning"
                        message = f"Slow Supabase: {latency:.2f}s"
                    else:
                        status = "critical"
                        message = f"Very slow Supabase: {latency:.2f}s"
                    
                    self.add_result("Supabase Performance", status, message, {
                        "latency_seconds": latency
                    })
                    
                except Exception as e:
                    self.add_result("Supabase Performance", "critical", f"Database error: {e}")
                    
        except Exception as e:
            self.add_result("Service Performance", "critical", f"Performance check error: {e}")
    
    def check_file_permissions(self) -> None:
        """Check file permissions and accessibility."""
        important_files = [
            "crawled_pages.sql",
            "src/doc_fetcher_mcp.py", 
            "pyproject.toml"
        ]
        
        for file_path in important_files:
            full_path = self.project_root / file_path
            
            if not full_path.exists():
                self.add_result(f"File Access: {file_path}", "critical", "File does not exist")
                continue
                
            try:
                # Check read permission
                with open(full_path, 'r') as f:
                    f.read(100)  # Read first 100 chars
                
                self.add_result(f"File Access: {file_path}", "healthy", "File is readable")
                
            except PermissionError:
                self.add_result(f"File Access: {file_path}", "critical", "Permission denied")
            except Exception as e:
                self.add_result(f"File Access: {file_path}", "warning", f"Access error: {e}")
    
    def check_network_connectivity(self) -> None:
        """Check network connectivity to required services."""
        import urllib.request
        import socket
        
        services = [
            ("OpenAI API", "https://api.openai.com"),
            ("Supabase", "https://supabase.com")
        ]
        
        for service_name, url in services:
            try:
                start_time = time.time()
                response = urllib.request.urlopen(url, timeout=10)
                latency = time.time() - start_time
                
                if response.code == 200:
                    self.add_result(f"Network: {service_name}", "healthy", 
                                  f"Connected in {latency:.2f}s")
                else:
                    self.add_result(f"Network: {service_name}", "warning",
                                  f"HTTP {response.code}")
                    
            except socket.timeout:
                self.add_result(f"Network: {service_name}", "critical", "Connection timeout")
            except Exception as e:
                self.add_result(f"Network: {service_name}", "warning", f"Connection error: {e}")
    
    def _load_env_vars(self) -> Dict[str, str]:
        """Load environment variables from .env file."""
        env_vars = {}
        env_file = self.project_root / ".env"
        
        if env_file.exists():
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        env_vars[key.strip()] = value.strip()
        
        return env_vars
    
    async def run_health_check(self, full_check: bool = False) -> bool:
        """Run comprehensive health check."""
        print("🏥 Doc-Monitor-MCP Health Check")
        print("=" * 50)
        
        # Basic checks
        print("🔍 Running basic health checks...")
        self.check_system_resources()
        self.check_file_permissions()
        
        # Extended checks
        if full_check:
            print("🔬 Running extended diagnostics...")
            self.check_network_connectivity()
            await self.check_database_schema()
            await self.check_service_performance()
        
        # Display results
        self.display_results()
        
        # Return overall health status
        critical_issues = any(r.status == "critical" for r in self.results)
        return not critical_issues
    
    def display_results(self) -> None:
        """Display health check results."""
        print("\n" + "=" * 50)
        print("🏥 HEALTH CHECK RESULTS")
        print("=" * 50)
        
        # Group results by status
        healthy = [r for r in self.results if r.status == "healthy"]
        warnings = [r for r in self.results if r.status == "warning"]
        critical = [r for r in self.results if r.status == "critical"]
        
        # Display healthy checks
        if healthy:
            print(f"\n💚 HEALTHY ({len(healthy)} checks)")
            for result in healthy:
                print(f"   ✓ {result.component}: {result.message}")
        
        # Display warnings
        if warnings:
            print(f"\n💛 WARNINGS ({len(warnings)} checks)")
            for result in warnings:
                print(f"   ⚠ {result.component}: {result.message}")
        
        # Display critical issues
        if critical:
            print(f"\n❤️ CRITICAL ({len(critical)} checks)")
            for result in critical:
                print(f"   ✗ {result.component}: {result.message}")
        
        # Overall status
        total = len(self.results)
        print(f"\n📊 SUMMARY: {len(healthy)} healthy, {len(warnings)} warnings, {len(critical)} critical")
        
        if critical:
            print("\n🚨 CRITICAL ISSUES FOUND!")
            print("   System may not function properly.")
            print("   Run 'make validate' for detailed fixes.")
        elif warnings:
            print("\n⚠️ Some issues detected.")
            print("   System should work but may have performance issues.")
        else:
            print("\n✨ All systems healthy!")

def main():
    """Main health check function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run Doc-Monitor-MCP health checks")
    parser.add_argument("--full", action="store_true",
                       help="Run extended diagnostics including network and performance tests")
    parser.add_argument("--json", action="store_true",
                       help="Output results as JSON")
    
    args = parser.parse_args()
    
    # Install psutil if not available
    try:
        import psutil
    except ImportError:
        print("Installing psutil for system monitoring...")
        os.system("uv add psutil")
        import psutil
    
    checker = HealthChecker()
    
    # Run health check
    healthy = asyncio.run(checker.run_health_check(full_check=args.full))
    
    # JSON output
    if args.json:
        results_dict = {
            "healthy": healthy,
            "results": [
                {
                    "component": r.component,
                    "status": r.status,
                    "message": r.message,
                    "metrics": r.metrics
                }
                for r in checker.results
            ]
        }
        print(json.dumps(results_dict, indent=2))
    
    # Exit with appropriate code
    sys.exit(0 if healthy else 1)

if __name__ == "__main__":
    main() 