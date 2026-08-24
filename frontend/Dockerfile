# syntax=docker/dockerfile:1
# Node 22: Vite 8 requires ^20.19 || >=22.12.
FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
