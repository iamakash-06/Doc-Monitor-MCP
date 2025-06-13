#!/bin/bash
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
