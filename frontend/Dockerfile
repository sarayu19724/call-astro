# Build Stage
FROM node:20-alpine AS build

WORKDIR /app

# Install package dependencies
COPY package*.json ./
RUN npm install

# Copy source and build
COPY . .
RUN npm run build

# Production Stage
FROM nginx:alpine

# Copy built files from build stage to nginx html root
COPY --from=build /app/dist /usr/share/nginx/html

# Copy custom nginx configuration for routing
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
