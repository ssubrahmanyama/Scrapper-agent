# ── Stage 1: Build ──────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY . .

ARG VITE_API_URL=https://api.privacyshield.ai/api/v1
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

# ── Stage 2: Serve with nginx ────────────────────────────────────────────────
FROM nginx:1.27-alpine AS runtime

# Remove default config
RUN rm -rf /etc/nginx/conf.d/* /etc/nginx/nginx.conf

# Write nginx.conf inline (avoids needing a separate file)
RUN printf 'user nginx;\nworker_processes auto;\nerror_log /var/log/nginx/error.log warn;\npid /var/run/nginx.pid;\nevents { worker_connections 1024; }\nhttp {\n  include /etc/nginx/mime.types;\n  default_type application/octet-stream;\n  server_tokens off;\n  sendfile on;\n  keepalive_timeout 65;\n  gzip on;\n  gzip_types text/plain text/css application/json application/javascript text/javascript image/svg+xml;\n  include /etc/nginx/conf.d/*.conf;\n}\n' > /etc/nginx/nginx.conf
COPY nginx/default.conf /etc/nginx/conf.d/default.conf

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

# AppSec: run nginx as non-root
RUN chown -R nginx:nginx /usr/share/nginx/html \
    && chmod -R 755 /usr/share/nginx/html

# Remove server version from headers (set in nginx.conf)
EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s CMD wget -q -O - http://localhost/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
