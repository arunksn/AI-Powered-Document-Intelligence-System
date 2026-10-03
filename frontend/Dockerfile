FROM node:20-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-slim
WORKDIR /app
RUN npm install -g serve
COPY --from=build /app/dist ./dist
ENV NODE_ENV=production
EXPOSE 5173
CMD ["sh", "-c", "serve -s dist -l ${PORT:-5173}"]
