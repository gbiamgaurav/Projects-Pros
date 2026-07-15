FROM python:3.11-slim

# System deps (psycopg[binary] ships its own libpq, but curl is handy for healthchecks)
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code (backend + tools + templates + static)
COPY . .

EXPOSE 8000

# Serves both the API (backend) and the UI (templates/static) from one process
CMD ["uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8000"]
