FROM node:18-alpine

WORKDIR /app

# Install MockPass locally
RUN npm install @opengovsg/mockpass express

# Copy custom server wrapper and repo-managed MyInfo personas
COPY services/mockpass/server.js /app/server.js
COPY services/mockpass/v3.json /app/v3.json

# Expose port
EXPOSE 5156

# Start custom MockPass server (which wraps the default MockPass)
CMD ["node", "/app/server.js"]
