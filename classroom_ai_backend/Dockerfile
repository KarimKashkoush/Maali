FROM node:24-bookworm-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY src ./src
COPY migrations ./migrations
RUN mkdir -p /app/uploads && chown node:node /app/uploads
ENV NODE_ENV=production PORT=4000
USER node
EXPOSE 4000
CMD ["node", "src/server.js"]
