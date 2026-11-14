#!/usr/bin/env bash
# Samples CPU% and RSS (MB) of the API, worker, PostgreSQL and Redis every 2 s until killed.
# Usage: loadtest/sample_resources.sh > load-results/resources.csv
echo "timestamp,process,cpu_percent,rss_mb"
while true; do
  ts=$(date +%s)
  for name in uvicorn "arq worker" postgres redis-server; do
    ps -eo pcpu=,rss=,args= | grep -F "$name" | grep -v grep | awk -v ts="$ts" -v n="$name" \
      '{cpu+=$1; rss+=$2} END {printf "%s,%s,%.1f,%.1f\n", ts, n, cpu, rss/1024}'
  done
  sleep 2
done
