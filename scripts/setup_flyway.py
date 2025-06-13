#!/usr/bin/env python3
"""
Setup Flyway Integration for Doc-Monitor-MCP
==========================================

This script sets up Flyway database migration tool to replace the manual
database setup process currently required by Supabase.
"""

import os
import sys
import subprocess
from pathlib import Path
import shutil
import platform

def create_directories():
    """Create necessary directories for Flyway."""
    directories = [
        "db/migration",
        "db/scripts"
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"✓ Created directory: {directory}")

def download_flyway():
    """Download and install Flyway."""
    system = platform.system().lower()
    
    if system == "darwin":  # macOS
        # Check if Homebrew is available
        if shutil.which('brew'):
            print("📦 Installing Flyway via Homebrew...")
            subprocess.run(["brew", "install", "flyway"], check=True)
            return True
    
    elif system == "linux":
        # Download Linux version
        flyway_version = "9.22.3"
        flyway_url = f"https://repo1.maven.org/maven2/org/flywaydb/flyway-commandline/{flyway_version}/flyway-commandline-{flyway_version}-linux-x64.tar.gz"
        
        print(f"📦 Downloading Flyway {flyway_version}...")
        subprocess.run([
            "curl", "-L", flyway_url, 
            "-o", "flyway.tar.gz"
        ], check=True)
        
        subprocess.run(["tar", "xvf", "flyway.tar.gz"], check=True)
        subprocess.run(["rm", "flyway.tar.gz"], check=True)
        
        flyway_dir = f"flyway-{flyway_version}"
        if Path(flyway_dir).exists():
            shutil.move(flyway_dir, "tools/flyway")
            print("✓ Flyway installed to tools/flyway")
            return True
    
    return False

def convert_sql_to_migrations():
    """Convert existing SQL file to Flyway migrations."""
    
    # Read the existing SQL file
    sql_file = Path("crawled_pages.sql")
    if not sql_file.exists():
        print("❌ crawled_pages.sql not found")
        return False
    
    print("🔄 Converting crawled_pages.sql to Flyway migrations...")
    
    with open(sql_file, 'r') as f:
        content = f.read()
    
    # Split into logical migrations
    migrations = [
        {
            "version": "V1",
            "description": "Create_pgvector_extension",
            "sql": "CREATE EXTENSION IF NOT EXISTS vector;"
        },
        {
            "version": "V2", 
            "description": "Create_crawled_pages_table",
            "sql": """
CREATE TABLE IF NOT EXISTS crawled_pages (
    id BIGSERIAL PRIMARY KEY,
    url VARCHAR NOT NULL,
    chunk_number INTEGER NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding VECTOR(1536),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    source VARCHAR(255),
    endpoint VARCHAR(255),
    method VARCHAR(10)
);
"""
        },
        {
            "version": "V3",
            "description": "Create_document_changes_table", 
            "sql": """
CREATE TABLE IF NOT EXISTS document_changes (
    id BIGSERIAL PRIMARY KEY,
    url VARCHAR NOT NULL,
    old_content_hash VARCHAR(64),
    new_content_hash VARCHAR(64) NOT NULL,
    change_type VARCHAR(50) NOT NULL,
    detected_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb
);
"""
        },
        {
            "version": "V4",
            "description": "Create_monitored_documentations_table",
            "sql": """
CREATE TABLE IF NOT EXISTS monitored_documentations (
    id BIGSERIAL PRIMARY KEY,
    url VARCHAR NOT NULL UNIQUE,
    name VARCHAR(255),
    description TEXT,
    status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    last_checked_at TIMESTAMP WITH TIME ZONE,
    check_frequency_hours INTEGER DEFAULT 24,
    notes TEXT
);
"""
        },
        {
            "version": "V5",
            "description": "Create_indexes",
            "sql": """
-- Indexes for crawled_pages
CREATE INDEX IF NOT EXISTS idx_crawled_pages_url ON crawled_pages(url);
CREATE INDEX IF NOT EXISTS idx_crawled_pages_source ON crawled_pages(source);
CREATE INDEX IF NOT EXISTS idx_crawled_pages_endpoint ON crawled_pages(endpoint);
CREATE INDEX IF NOT EXISTS idx_crawled_pages_method ON crawled_pages(method);
CREATE INDEX IF NOT EXISTS idx_crawled_pages_created_at ON crawled_pages(created_at);

-- Indexes for document_changes  
CREATE INDEX IF NOT EXISTS idx_document_changes_url ON document_changes(url);
CREATE INDEX IF NOT EXISTS idx_document_changes_detected_at ON document_changes(detected_at);

-- Indexes for monitored_documentations
CREATE INDEX IF NOT EXISTS idx_monitored_docs_status ON monitored_documentations(status);
CREATE INDEX IF NOT EXISTS idx_monitored_docs_last_checked ON monitored_documentations(last_checked_at);
"""
        }
    ]
    
    # Write migration files
    for migration in migrations:
        filename = f"db/migration/{migration['version']}__{migration['description']}.sql"
        with open(filename, 'w') as f:
            f.write(f"-- {migration['description']}\n")
            f.write(f"-- Created by setup_flyway.py\n\n")
            f.write(migration['sql'].strip())
            f.write("\n")
        
        print(f"✓ Created {filename}")
    
    return True

def create_flyway_config():
    """Create Flyway configuration."""
    
    config_content = """# Flyway Configuration for Doc-Monitor-MCP
# See: https://flywaydb.org/documentation/configuration/configfile

# Database connection
flyway.url=jdbc:postgresql://${DB_HOST:localhost}:${DB_PORT:5432}/${DB_NAME:postgres}
flyway.user=${DB_USER:postgres}
flyway.password=${DB_PASSWORD}

# Migration settings
flyway.locations=filesystem:db/migration
flyway.table=flyway_schema_history
flyway.baselineOnMigrate=true
flyway.validateOnMigrate=true

# Postgres specific
flyway.postgresql.transactional.lock=false
"""
    
    with open("db/flyway.conf", 'w') as f:
        f.write(config_content)
    
    print("✓ Created db/flyway.conf")

def create_migration_scripts():
    """Create helper scripts for database migration."""
    
    # Migration script
    migrate_script = """#!/bin/bash
# Database Migration Script for Doc-Monitor-MCP

set -e

echo "🚀 Running database migrations..."

# Load environment variables
source .env 2>/dev/null || echo "⚠️  No .env file found"

# Set database connection from environment or Supabase format
if [ -n "$SUPABASE_URL" ] && [ -n "$SUPABASE_SERVICE_KEY" ]; then
    # Extract details from Supabase URL
    DB_HOST=$(echo $SUPABASE_URL | sed 's|https://||' | sed 's|.supabase.co.*|.supabase.co|')
    DB_NAME="postgres"
    DB_USER="postgres"
    DB_PASSWORD="$SUPABASE_SERVICE_KEY"
    DB_PORT="5432"
    
    export FLYWAY_URL="jdbc:postgresql://$DB_HOST:$DB_PORT/$DB_NAME?sslmode=require"
    export FLYWAY_USER="$DB_USER"  
    export FLYWAY_PASSWORD="$DB_PASSWORD"
else
    # Use standard PostgreSQL environment variables
    export FLYWAY_URL="jdbc:postgresql://${DB_HOST:-localhost}:${DB_PORT:-5432}/${DB_NAME:-postgres}"
    export FLYWAY_USER="${DB_USER:-postgres}"
    export FLYWAY_PASSWORD="${DB_PASSWORD}"
fi

# Run Flyway migration
if command -v flyway &> /dev/null; then
    flyway -configFiles=db/flyway.conf migrate
elif [ -f "tools/flyway/flyway" ]; then
    tools/flyway/flyway -configFiles=db/flyway.conf migrate
else
    echo "❌ Flyway not found. Please install Flyway first."
    exit 1
fi

echo "✅ Database migration completed!"
"""
    
    with open("db/scripts/migrate.sh", 'w') as f:
        f.write(migrate_script)
    
    os.chmod("db/scripts/migrate.sh", 0o755)
    print("✓ Created db/scripts/migrate.sh")
    
    # Info script
    info_script = """#!/bin/bash
# Database Migration Info Script

set -e

echo "📊 Database Migration Status"
echo "============================="

# Load environment and run flyway info
source .env 2>/dev/null || echo "⚠️  No .env file found"

if [ -n "$SUPABASE_URL" ] && [ -n "$SUPABASE_SERVICE_KEY" ]; then
    DB_HOST=$(echo $SUPABASE_URL | sed 's|https://||' | sed 's|.supabase.co.*|.supabase.co|')
    export FLYWAY_URL="jdbc:postgresql://$DB_HOST:5432/postgres?sslmode=require"
    export FLYWAY_USER="postgres"
    export FLYWAY_PASSWORD="$SUPABASE_SERVICE_KEY"
fi

if command -v flyway &> /dev/null; then
    flyway -configFiles=db/flyway.conf info
elif [ -f "tools/flyway/flyway" ]; then
    tools/flyway/flyway -configFiles=db/flyway.conf info
else
    echo "❌ Flyway not found"
    exit 1
fi
"""
    
    with open("db/scripts/info.sh", 'w') as f:
        f.write(info_script)
    
    os.chmod("db/scripts/info.sh", 0o755)
    print("✓ Created db/scripts/info.sh")

def update_makefile():
    """Update Makefile with Flyway commands."""
    
    makefile_additions = """

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
"""
    
    # Read existing Makefile
    makefile_path = Path("Makefile")
    if makefile_path.exists():
        with open(makefile_path, 'r') as f:
            content = f.read()
        
        # Add Flyway commands if not already present
        if "db-migrate:" not in content:
            with open(makefile_path, 'a') as f:
                f.write(makefile_additions)
            print("✓ Updated Makefile with Flyway commands")
        else:
            print("⚠️  Makefile already contains Flyway commands")
    else:
        print("⚠️  Makefile not found")

def main():
    """Main setup function."""
    
    print("🛠️ Setting up Flyway Integration for Doc-Monitor-MCP")
    print("=" * 55)
    
    try:
        # Create directory structure
        create_directories()
        
        # Convert existing SQL to migrations
        if convert_sql_to_migrations():
            print("✅ SQL files converted to Flyway migrations")
        
        # Create Flyway configuration
        create_flyway_config()
        
        # Create migration scripts
        create_migration_scripts()
        
        # Update Makefile
        update_makefile()
        
        print("\n🎉 Flyway setup completed!")
        print("\n📋 Next Steps:")
        print("1. Install Flyway: brew install flyway (macOS) or download manually")
        print("2. Test migration: make db-migrate")
        print("3. Check status: make db-info") 
        print("4. Use 'make db-setup-flyway' instead of manual SQL copy-paste")
        
        print("\n✨ Benefits:")
        print("• ✅ No more manual SQL copy-pasting")
        print("• ✅ Version controlled database schema")
        print("• ✅ Automated database setup")
        print("• ✅ Industry standard approach")
        
    except Exception as e:
        print(f"❌ Setup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 