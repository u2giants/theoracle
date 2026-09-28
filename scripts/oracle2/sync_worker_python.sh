#!/bin/sh
# Copy the Oracle 2 Python package next to the worker Trigger configs.
set -eu
root=$(cd "$(dirname "$0")/../.." && pwd)
dest="$root/apps/workers/oracle2-python"
rm -rf "$dest"
mkdir -p "$dest"
cp -R "$root/services/oracle-brain/oracle_brain" "$dest/oracle_brain"
find "$dest" -name '__pycache__' -type d -prune -exec rm -rf {} +
