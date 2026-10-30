# Reviewed toolchain. Record the resulting image ID in every verification report.
FROM mcr.microsoft.com/playwright:v1.62.1-noble
RUN npm install --global pnpm@10.18.2
RUN npm install --prefix /opt/guardian-parser --ignore-scripts --no-package-lock typescript@6.0.3
RUN node -e "const ts=require('/opt/guardian-parser/node_modules/typescript');if(ts.version!=='6.0.3')process.exit(1)"
ENV CI=true NEXT_TELEMETRY_DISABLED=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
