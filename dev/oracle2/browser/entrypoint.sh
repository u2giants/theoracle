#!/bin/sh
set -eu
# Reject loaders before Node can evaluate any input-controlled executable code.
[ "${ORACLE2_NATIVE_BROWSER_ONLY:-}" = 1 ] || exit 78
[ "${NODE_ENV:-}" = production ] || exit 78
[ "${NODE_OPTIONS+x}" != x ] || exit 78
[ "${NODE_PATH+x}" != x ] || exit 78
ulimit -c 0
exec /usr/local/bin/node /app/native-browser-launcher.mjs
