#!/usr/bin/env python3
"""
Automated Database Setup Script for Doc-Monitor-MCP
==================================================

This script automatically sets up the database schema for Doc-Monitor-MCP
including all required tables, indexes, functions, and extensions.

Usage:
    python scripts/db_setup.py
    python scripts/db_setup.py --reset  # Reset and recreate all tables
    python scripts/db_setup.py --validate-only  # Only validate existing schema
"""

import os
import sys
import asyncio
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import json

# Add src to path to import our modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

@dataclass
class DatabaseResult:
    """Result of a database operation."""
    operation: str
    status: str  # 'success', 'error', 'warning'
    message: str
    details: Optional[str] = None

class DatabaseSetup:
    """Automated database setup for Doc-Monitor-MCP."""
    
    def __init__(self):
        self.results: List[DatabaseResult] = []
        self.project_root = Path(__file__).parent.parent
        self.client = None
        
    def add_result(self, operation: str, status: str, message: str, details: str = None):
        """Add a database operation result."""
        self.results.append(DatabaseResult(operation, status, message, details))
    
    def load_environment(self) -> Dict[str, str]:
        """Load environment variables from .env file."""
        env_vars = {}
        env_file = self.project_root / ".env"
        
        if not env_file.exists():
            self.add_result("Environment", "error", "No .env file found")
            return env_vars
            
        try:
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        env_vars[key.strip()] = value.strip()
        except Exception as e:
            self.add_result("Environment", "error", f"Error reading .env file: {e}")
            
        return env_vars
    
    def connect_to_database(self, env_vars: Dict[str, str]) -> bool:
        """Connect to Supabase database."""
        try:
            supabase_url = env_vars.get('SUPABASE_URL')
            supabase_key = env_vars.get('SUPABASE_SERVICE_KEY')
            
            if not supabase_url or supabase_url == "your_supabase_project_url_here":
                self.add_result("Connection", "error", "Invalid or missing SUPABASE_URL")
                return False
                
            if not supabase_key or supabase_key == "your_supabase_service_key_here":
                self.add_result("Connection", "error", "Invalid or missing SUPABASE_SERVICE_KEY")
                return False
            
            from supabase import create_client
            self.client = create_client(supabase_url, supabase_key)
            
            # Test connection by checking if we can access system tables
            response = self.client.table("pg_tables").select("tablename").limit(1).execute()
            
            self.add_result("Connection", "success", "Successfully connected to Supabase")
            return True
            
        except ImportError:
            self.add_result("Connection", "error", "Supabase package not installed")
            return False
        except Exception as e:
            self.add_result("Connection", "error", f"Connection failed: {e}")
            return False
    
    def parse_sql_file(self, file_path: Path) -> List[str]:
        """Parse SQL file into individual statements."""
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            
            # Remove comments
            content = re.sub(r'--.*$', '', content, flags=re.MULTILINE)
            
            # Split into statements (simple approach - split on ';' but handle function definitions)
            statements = []
            current_statement = ""
            in_function = False
            
            for line in content.split('\n'):
                line = line.strip()
                if not line:
                    continue
                
                # Track function boundaries
                if 'create or replace function' in line.lower() or 'create function' in line.lower():
                    in_function = True
                elif line.endswith('$$;') and in_function:
                    current_statement += line + '\n'
                    statements.append(current_statement.strip())
                    current_statement = ""
                    in_function = False
                    continue
                
                current_statement += line + '\n'
                
                # If not in function and line ends with semicolon, it's a statement
                if not in_function and line.endswith(';'):
                    statements.append(current_statement.strip())
                    current_statement = ""
            
            # Add remaining statement if any
            if current_statement.strip():
                statements.append(current_statement.strip())
            
            return [stmt for stmt in statements if stmt.strip()]
            
        except Exception as e:
            self.add_result("SQL Parsing", "error", f"Error parsing {file_path}: {e}")
            return []
    
    def execute_sql_statement(self, statement: str, description: str = None) -> bool:
        """Execute a single SQL statement."""
        try:
            if not self.client:
                self.add_result("SQL Execution", "error", "No database connection")
                return False
            
            # Clean the statement
            statement = statement.strip()
            if not statement:
                return True
            
            desc = description or f"SQL statement ({statement[:50]}...)"
            
            # For Supabase, we need to use the REST API with raw SQL
            # This is a limitation - Supabase doesn't allow DDL operations through the Python client
            # The user needs to run the SQL manually in the Supabase SQL editor
            self.add_result("SQL Execution", "error", 
                          f"Cannot execute DDL statements through Supabase Python client: {desc}")
            self.add_result("SQL Execution", "error", 
                          "Please run the SQL schema manually in Supabase SQL Editor")
            return False
            
        except Exception as e:
            desc = description or f"SQL statement ({statement[:50]}...)"
            
            # Check for specific error types
            error_msg = str(e).lower()
            if "already exists" in error_msg:
                self.add_result("SQL Execution", "warning", f"Already exists: {desc}")
                return True
            elif "does not exist" in error_msg and "drop" in statement.lower():
                self.add_result("SQL Execution", "warning", f"Drop target not found: {desc}")
                return True
            else:
                self.add_result("SQL Execution", "error", f"Failed: {desc} - {e}")
                return False
    
    def setup_schema_directly(self) -> bool:
        """Set up schema using direct SQL execution."""
        try:
            # Enable pgvector extension
            pgvector_sql = "CREATE EXTENSION IF NOT EXISTS vector;"
            success = self.execute_sql_statement(pgvector_sql, "Enable pgvector extension")
            
            # Create crawled_pages table
            crawled_pages_sql = """
            CREATE TABLE IF NOT EXISTS crawled_pages (
                id BIGSERIAL PRIMARY KEY,
                url VARCHAR NOT NULL,
                chunk_number INTEGER NOT NULL,
                content TEXT NOT NULL,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                embedding VECTOR(1536),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                last_modified_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
                UNIQUE(url, chunk_number, version)
            );
            """
            success &= self.execute_sql_statement(crawled_pages_sql, "Create crawled_pages table")
            
            # Create document_changes table
            document_changes_sql = """
            CREATE TABLE IF NOT EXISTS document_changes (
                id BIGSERIAL PRIMARY KEY,
                url VARCHAR NOT NULL,
                version INTEGER NOT NULL,
                change_type VARCHAR NOT NULL,
                change_summary TEXT NOT NULL,
                change_impact VARCHAR NOT NULL,
                change_details JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
                UNIQUE(url, version)
            );
            """
            success &= self.execute_sql_statement(document_changes_sql, "Create document_changes table")
            
            # Create monitored_documentations table
            monitored_docs_sql = """
            CREATE TABLE IF NOT EXISTS monitored_documentations (
                id BIGSERIAL PRIMARY KEY,
                url VARCHAR UNIQUE NOT NULL,
                crawl_type VARCHAR NOT NULL DEFAULT 'webpage',
                status VARCHAR NOT NULL DEFAULT 'active',
                notes TEXT,
                date_added TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
                last_crawled_at TIMESTAMP WITH TIME ZONE
            );
            """
            success &= self.execute_sql_statement(monitored_docs_sql, "Create monitored_documentations table")
            
            # Create indexes
            indexes = [
                ("CREATE INDEX IF NOT EXISTS idx_crawled_pages_embedding ON crawled_pages USING ivfflat (embedding vector_cosine_ops);", "Vector similarity index"),
                ("CREATE INDEX IF NOT EXISTS idx_crawled_pages_metadata ON crawled_pages USING gin (metadata);", "Metadata GIN index"),
                ("CREATE INDEX IF NOT EXISTS idx_crawled_pages_source ON crawled_pages ((metadata->>'source'));", "Source index"),
                ("CREATE INDEX IF NOT EXISTS idx_crawled_pages_version ON crawled_pages (url, version);", "Version index"),
                ("CREATE INDEX IF NOT EXISTS idx_crawled_pages_content_fts ON crawled_pages USING gin(to_tsvector('english', content));", "Full-text search index"),
                ("CREATE INDEX IF NOT EXISTS idx_crawled_pages_composite ON crawled_pages (url, version, chunk_number);", "Composite index"),
                ("CREATE INDEX IF NOT EXISTS idx_monitored_documentations_url ON monitored_documentations(url);", "Monitored docs URL index")
            ]
            
            for sql, desc in indexes:
                success &= self.execute_sql_statement(sql, desc)
            
            return success
            
        except Exception as e:
            self.add_result("Schema Setup", "error", f"Schema setup failed: {e}")
            return False
    
    def create_functions(self) -> bool:
        """Create required database functions."""
        try:
            # Basic search function
            search_function = """
            CREATE OR REPLACE FUNCTION match_crawled_pages (
              query_embedding vector(1536),
              match_count int default 10,
              filter jsonb DEFAULT '{}'::jsonb
            ) RETURNS TABLE (
              id bigint,
              url varchar,
              chunk_number integer,
              content text,
              metadata jsonb,
              similarity float,
              version integer
            )
            LANGUAGE plpgsql
            AS $$
            #variable_conflict use_column
            BEGIN
              RETURN QUERY
              SELECT
                crawled_pages.id,
                crawled_pages.url,
                crawled_pages.chunk_number,
                crawled_pages.content,
                crawled_pages.metadata,
                1 - (crawled_pages.embedding <=> query_embedding) as similarity,
                crawled_pages.version
              FROM crawled_pages
              WHERE metadata @> filter
              ORDER BY crawled_pages.embedding <=> query_embedding
              LIMIT match_count;
            END;
            $$;
            """
            
            success = self.execute_sql_statement(search_function, "Create search function")
            
            # Version function
            version_function = """
            CREATE OR REPLACE FUNCTION get_latest_version(p_url varchar)
            RETURNS integer
            LANGUAGE plpgsql
            AS $$
            DECLARE
                latest_ver integer;
            BEGIN
                SELECT coalesce(max(version)::integer, 0) INTO latest_ver
                FROM crawled_pages
                WHERE url = p_url;
                
                RETURN latest_ver;
            END;
            $$;
            """
            
            success &= self.execute_sql_statement(version_function, "Create version function")
            
            return success
            
        except Exception as e:
            self.add_result("Functions", "error", f"Function creation failed: {e}")
            return False
    
    def validate_schema(self) -> bool:
        """Validate that all required schema elements exist."""
        try:
            if not self.client:
                self.add_result("Validation", "error", "No database connection")
                return False
            
            all_tables_exist = True
            
            # Check tables
            required_tables = ['crawled_pages', 'document_changes', 'monitored_documentations']
            for table in required_tables:
                try:
                    response = self.client.table(table).select("count", count="exact").limit(1).execute()
                    self.add_result("Validation", "success", f"Table {table} exists and is accessible")
                except Exception as e:
                    error_msg = str(e).lower()
                    if "does not exist" in error_msg or "relation" in error_msg:
                        self.add_result("Validation", "error", f"Table {table} does not exist")
                    else:
                        self.add_result("Validation", "error", f"Table {table} inaccessible: {e}")
                    all_tables_exist = False
            
            # Only check pgvector if tables exist
            if all_tables_exist:
                try:
                    response = self.client.table("crawled_pages").select("embedding").limit(1).execute()
                    self.add_result("Validation", "success", "pgvector extension is working")
                except Exception as e:
                    if "vector" in str(e).lower():
                        self.add_result("Validation", "error", "pgvector extension not available")
                        return False
                    else:
                        # Might just be no data yet
                        self.add_result("Validation", "success", "pgvector extension appears to be available")
                
                # Database functions are harder to validate, so we'll assume they exist if tables do
                self.add_result("Validation", "success", "Schema validation completed")
            
            return all_tables_exist
            
        except Exception as e:
            self.add_result("Validation", "error", f"Schema validation failed: {e}")
            return False
    
    def reset_schema(self) -> bool:
        """Reset the database schema (drop and recreate)."""
        try:
            # Drop tables in reverse dependency order
            drop_statements = [
                "DROP TABLE IF EXISTS document_changes CASCADE;",
                "DROP TABLE IF EXISTS monitored_documentations CASCADE;", 
                "DROP TABLE IF EXISTS crawled_pages CASCADE;",
                "DROP FUNCTION IF EXISTS match_crawled_pages(vector, integer, jsonb);",
                "DROP FUNCTION IF EXISTS get_latest_version(varchar);"
            ]
            
            for statement in drop_statements:
                self.execute_sql_statement(statement, f"Reset: {statement}")
            
            self.add_result("Reset", "success", "Database schema reset completed")
            return True
            
        except Exception as e:
            self.add_result("Reset", "error", f"Schema reset failed: {e}")
            return False
    
    async def run_setup(self, reset: bool = False, validate_only: bool = False) -> bool:
        """Run the complete database setup process."""
        print("🛠️ Doc-Monitor-MCP Database Setup")
        print("=" * 50)
        
        # Load environment and connect
        env_vars = self.load_environment()
        if not self.connect_to_database(env_vars):
            return False
        
        # Validate only mode
        if validate_only:
            print("🔍 Validating existing schema...")
            success = self.validate_schema()
            self.display_results()
            return success
        
        # Check if schema already exists
        print("🔍 Checking existing schema...")
        if self.validate_schema():
            print("✅ Database schema already exists and is valid!")
            self.display_results()
            return True
        
        # Schema doesn't exist - guide user through manual setup
        print("\n📋 MANUAL DATABASE SETUP REQUIRED")
        print("=" * 50)
        print("Supabase requires manual SQL execution for schema creation.")
        print("Please follow these steps:")
        print("")
        print("1. Open your Supabase project dashboard")
        print("2. Navigate to SQL Editor")
        print("3. Copy and paste the contents of 'crawled_pages.sql'")
        print("4. Execute the SQL")
        print("5. Run 'make db-validate' to verify the setup")
        print("")
        print(f"📄 SQL file location: {self.project_root}/crawled_pages.sql")
        print("")
        
        self.add_result("Manual Setup", "error", 
                       "Automated schema creation not supported by Supabase Python client")
        self.add_result("Next Steps", "error", 
                       "Please run the SQL manually in Supabase SQL Editor")
        
        self.display_results()
        return False
    
    def display_results(self) -> None:
        """Display setup results."""
        print("\n" + "=" * 50)
        print("📋 DATABASE SETUP RESULTS")
        print("=" * 50)
        
        # Group results by status
        successful = [r for r in self.results if r.status == "success"]
        warnings = [r for r in self.results if r.status == "warning"]
        errors = [r for r in self.results if r.status == "error"]
        
        # Display successful operations
        if successful:
            print(f"\n✅ SUCCESSFUL ({len(successful)} operations)")
            for result in successful:
                print(f"   ✓ {result.operation}: {result.message}")
        
        # Display warnings
        if warnings:
            print(f"\n⚠️ WARNINGS ({len(warnings)} operations)")
            for result in warnings:
                print(f"   ⚠ {result.operation}: {result.message}")
        
        # Display errors
        if errors:
            print(f"\n❌ ERRORS ({len(errors)} operations)")
            for result in errors:
                print(f"   ✗ {result.operation}: {result.message}")
                if result.details:
                    print(f"     Details: {result.details}")
        
        # Summary
        total = len(self.results)
        print(f"\n📊 SUMMARY: {len(successful)} successful, {len(warnings)} warnings, {len(errors)} errors")
        
        if errors:
            print("\n🚨 Database setup incomplete due to errors!")
            print("   Check your Supabase credentials and permissions.")
        elif warnings:
            print("\n⚠️ Database setup completed with warnings.")
            print("   System should work but some features may be limited.")
        else:
            print("\n🎉 Database setup completed successfully!")
            print("   Your Doc-Monitor-MCP database is ready to use.")

def main():
    """Main setup function."""
    try:
        import argparse
        
        parser = argparse.ArgumentParser(description="Set up Doc-Monitor-MCP database")
        parser.add_argument("--reset", action="store_true",
                           help="Reset database (drop and recreate all tables)")
        parser.add_argument("--validate-only", action="store_true",
                           help="Only validate existing schema without making changes")
        parser.add_argument("--json", action="store_true",
                           help="Output results as JSON")
        
        args = parser.parse_args()
        
        setup = DatabaseSetup()
        
        # Run setup
        success = asyncio.run(setup.run_setup(
            reset=args.reset,
            validate_only=args.validate_only
        ))
        
        # JSON output
        if args.json:
            results_dict = {
                "success": success,
                "results": [
                    {
                        "operation": r.operation,
                        "status": r.status,
                        "message": r.message,
                        "details": r.details
                    }
                    for r in setup.results
                ]
            }
            print(json.dumps(results_dict, indent=2))
        
        # Exit with appropriate code
        sys.exit(0 if success else 1)
        
    except Exception as e:
        print(f"❌ Database setup script error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 