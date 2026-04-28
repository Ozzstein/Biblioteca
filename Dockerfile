FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Copy project files
COPY pyproject.toml uv.lock* ./
COPY src/ ./src/
COPY config/ ./config/
COPY graph/ ./graph/
COPY raw/ ./raw/
COPY retrieval/ ./retrieval/
COPY web/ ./web/
COPY wiki/ ./wiki/

# Install dependencies
RUN uv sync --extra web

# Set environment variables
ENV PYTHONPATH=/app/src
ENV BIBLIOTECA_HOME=/app/data

# Expose port
EXPOSE 8000

# Run web server
CMD ["uv", "run", "python", "-m", "uvicorn", "web.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
