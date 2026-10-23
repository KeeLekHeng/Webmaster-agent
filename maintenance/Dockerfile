# Reviewed toolchain. Record the resulting image ID in every verification report.
FROM mcr.microsoft.com/playwright:v1.62.1-noble
RUN npm install --global pnpm@10.18.2
ENV CI=true NEXT_TELEMETRY_DISABLED=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
