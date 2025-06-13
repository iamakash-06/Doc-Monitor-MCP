#!/bin/bash
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
