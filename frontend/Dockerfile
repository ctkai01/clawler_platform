# Production-only build (local dev still uses `npm run dev`, not this file).
# VITE_API_BASE_URL is baked into the JS bundle at build time — pass it as a
# build arg pointing at wherever the `api` service is actually reachable
# (VPS public IP:8083, or a domain once one exists).
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
