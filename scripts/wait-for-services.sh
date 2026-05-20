#!/usr/bin/env bash
# Wait for all infrastructure services to be healthy
set -e

MAX_WAIT=90
INTERVAL=3
ELAPSED=0

echo "Checking service health..."

check_service() {
    local name=$1
    local cmd=$2
    if eval "$cmd" > /dev/null 2>&1; then
        echo "  ✓ $name"
        return 0
    else
        return 1
    fi
}

while [ $ELAPSED -lt $MAX_WAIT ]; do
    ALL_HEALTHY=true

    check_service "PostgreSQL" "pg_isready -h localhost -p ${POSTGRES_PORT:-5432} -U ${POSTGRES_USER:-agentic}" || ALL_HEALTHY=false
    check_service "Redis" "redis-cli -p ${REDIS_PORT:-6379} ping" || ALL_HEALTHY=false
    check_service "Qdrant" "curl -sf http://localhost:${QDRANT_PORT:-6333}/healthz" || ALL_HEALTHY=false
    check_service "OpenSearch" "curl -sf http://localhost:${OPENSEARCH_PORT:-9200}/_cluster/health" || ALL_HEALTHY=false

    if [ "$ALL_HEALTHY" = true ]; then
        echo ""
        echo "All services healthy! (${ELAPSED}s)"
        exit 0
    fi

    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
    echo "  ... waiting (${ELAPSED}s / ${MAX_WAIT}s)"
done

echo "ERROR: Services did not become healthy within ${MAX_WAIT}s"
exit 1
