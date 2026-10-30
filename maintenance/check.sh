#!/bin/bash
# Runs ONLY in the isolated container with disposable test keys. No publish capability.
set -euo pipefail
cd /work
case "${1:?stage}" in
  lint) pnpm run lint ;;
  typecheck) pnpm run typecheck ;;
  unit) node --experimental-strip-types --test tests/unit/*.test.mjs ;;
  build) node /trusted/build.cjs ;;
  integration) E2E_TEST_DATA=1 node --experimental-strip-types --test --test-concurrency=1 tests/integration/*.test.mjs ;;
  browser) pnpm exec playwright test --config=/trusted/browser.config.ts --update-snapshots=none --workers=2 --max-failures=1 ;;
  *) exit 2 ;;
esac
