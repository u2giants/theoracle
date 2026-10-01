#!/bin/bash
set -o pipefail
cd /c/repos/oracle-s03-acceptance || exit 1
{
  echo "START $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  git rev-parse HEAD
  echo "PROVIDER=${1:-codex}"
  echo "MODE=${2:-plan-review}"
  ai-review "${1:-codex}" "${2:-plan-review}" --implementer mimo
  rc=$?
  echo "EXIT=$rc"
  echo "END $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo DONE > /c/repos/oracle-s03-acceptance/.ai-review-done.txt
  exit $rc
} >> /c/repos/oracle-s03-acceptance/.ai-review-out.txt 2>&1
