FROM node:20-alpine AS base

WORKDIR /app

COPY web/package*.json ./

RUN npm install

COPY web ./

ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

RUN npm run build

EXPOSE 3000

CMD ["npm", "run", "start"]

