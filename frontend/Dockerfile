FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package.json ./package.json
RUN npm install
COPY frontend/src ./src
COPY frontend/index.html ./index.html
COPY frontend/vite.config.ts ./vite.config.ts
RUN npm run build
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
