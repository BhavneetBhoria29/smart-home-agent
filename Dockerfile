FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Agent package (ADK serves each folder in /app/agents as an agent)
COPY smart_home_agent/ ./agents/smart_home_agent/

# Catalogue: loader.py reads data/products/info/*.json relative to /app
COPY data/ ./data/

RUN useradd --create-home app && chown -R app /app /usr/local/lib/python3.12/site-packages/google/adk/cli/browser
USER app

EXPOSE 8080
CMD ["sh", "-c", "adk web --host 0.0.0.0 --port 8080 --allow_origins \"${ALLOW_ORIGINS:-http://localhost:8080}\" /app/agents"]
