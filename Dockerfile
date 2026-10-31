FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml .
COPY app ./app
COPY alembic.ini .
COPY migrations ./migrations
RUN pip install --no-cache-dir .

CMD ["python", "-m", "app.main"]