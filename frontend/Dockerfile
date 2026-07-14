# syntax=docker/dockerfile:1
# peakatail-hub frontend: build the Vite SPA, serve it via nginx, proxy /api -> backend.
# Build context is the repo root (compose sets it) so this copies frontend/.
FROM node:20-slim AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# hit the real backend through nginx's /api proxy (not the in-memory mocks)
ENV VITE_USE_MOCKS=false
RUN npm run build

FROM nginx:1.27-alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
