FROM node:20-alpine AS base
WORKDIR /app

# Build-time API URL for Next.js (NEXT_PUBLIC_ is baked into the bundle)
ARG NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}

COPY package.json ./
RUN npm install --include=dev
COPY . .
RUN npm run build

FROM node:20-alpine
WORKDIR /app
ENV NODE_ENV=production
# Add curl for Docker healthchecks
RUN apk add --no-cache curl
COPY --from=base /app .
EXPOSE 3000
CMD ["npm", "run", "start", "--", "-H", "0.0.0.0", "-p", "3000"]
