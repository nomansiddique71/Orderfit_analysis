# --- stage 1: build the SolvOrder React UI ---------------------------------
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# --- stage 2: Python API + engine, serving the built UI --------------------
FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=web /web/dist /app/web/dist

ENV PORT=8080
EXPOSE 8080

# UI=streamlit runs the previous Streamlit interface instead (fallback flag).
CMD ["sh", "-c", "if [ \"$UI\" = streamlit ]; then exec streamlit run app.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true; else exec uvicorn server:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'; fi"]
