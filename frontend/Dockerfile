FROM node:22-alpine AS base

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm install

# --- Development (소스는 볼륨 마운트) ---
FROM base AS dev
EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--host"]

# --- Build ---
FROM base AS build
COPY . .
RUN npm run build

# --- Production (Nginx 정적 서빙 + API 리버스 프록시) ---
FROM nginx:alpine AS prod
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
