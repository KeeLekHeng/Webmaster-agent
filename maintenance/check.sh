#!/bin/bash
# Runs ONLY in the credential-free network-none container. No publish capability.
set -euo pipefail
cd /work
case "${1:?stage}" in
  lint) pnpm run lint ;;
  typecheck) pnpm run typecheck ;;
  unit) node --experimental-strip-types --test tests/unit/*.test.mjs ;;
  build) node /trusted/build.cjs ;;
  integration) node --experimental-strip-types --test --test-concurrency=1 tests/integration/*.test.mjs ;;
  browser) pnpm exec playwright test --workers=2 ;;
  *) exit 2 ;;
esac
