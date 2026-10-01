# Angular 21 exige Node >= 20.19 / 22.12 / 24 — nada no repo fixava isso
# (sem .nvmrc, sem "engines" no package.json), então o fallback é o Node
# mais recente disponível nesta imagem.
FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# Saída do novo builder @angular/build:application — sem outputPath
# customizado em angular.json, o default é dist/grupoConceitoMCP/browser.
FROM nginx:alpine

COPY --from=build /app/dist/grupoConceitoMCP/browser /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
