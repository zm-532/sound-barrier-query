FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src/ ./src/
COPY docs/*.xlsx ./docs/

RUN pip install --no-cache-dir .

EXPOSE 8765

CMD ["sound-barrier-query", "--host", "0.0.0.0", "--port", "8765"]
