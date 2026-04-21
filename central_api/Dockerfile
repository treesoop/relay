FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml ./
COPY README.md ./
COPY central_api ./central_api
COPY local_mcp ./local_mcp

RUN pip install --no-cache-dir -e ".[dev]"

EXPOSE 8080
CMD ["uvicorn", "--factory", "central_api.main:create_app", "--host", "0.0.0.0", "--port", "8080"]
