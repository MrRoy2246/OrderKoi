# OrderKoi frontend — build with Vite, serve with nginx.
#
# VITE_API_URL is baked into the JS bundle at build time
# (src/api/client.js), so it's a build ARG, not a runtime env —
# changing the API address means rebuilding the image.

FROM node:22-alpine AS build
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL
WORKDIR /app

# Dependencies first — cached unless package-lock.json changes
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build


FROM nginx:1.27-alpine

# nginx's docker entrypoint renders templates/*.template through
# envsubst into conf.d/ — that's how the API origin gets into the
# CSP header at container start (API_ORIGIN env var, set by compose).
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
