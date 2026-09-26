FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ADK serves every folder inside /app/agents as an agent.
# The package must expose `root_agent` (agent.py) and import it in __init__.py.
COPY smart_home_agent/ ./agents/smart_home_agent/

# If the Bauhaus catalogue JSONs live outside the package, copy them too and
# make sure the tools resolve the path relative to the package, e.g.:
# COPY data/ ./agents/smart_home_agent/data/

RUN useradd --create-home app && chown -R app /app
USER app

EXPOSE 8080

# `adk web` = API + built-in chat UI (good for a live demo link).
# Swap to `adk api_server` for an API-only deployment.
CMD ["adk", "web", "--host", "0.0.0.0", "--port", "8080", "/app/agents"]
