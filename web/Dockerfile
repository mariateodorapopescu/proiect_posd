FROM node:22.22.0-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_AUTHORITY=http://localhost:8080/realms/securesync
ARG VITE_API_URL=http://localhost:8081
ARG VITE_DOCUMENTE_URL=http://localhost:3001/
ARG VITE_PORTAL_URL=http://localhost:3002/
ENV VITE_AUTHORITY=$VITE_AUTHORITY VITE_API_URL=$VITE_API_URL VITE_DOCUMENTE_URL=$VITE_DOCUMENTE_URL VITE_PORTAL_URL=$VITE_PORTAL_URL
RUN npm run build

FROM nginx:1.28-alpine
ARG APP_NAME=documente
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/${APP_NAME}/ /usr/share/nginx/html/
EXPOSE 80
