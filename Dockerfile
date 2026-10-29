FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY fixtures ./fixtures
COPY tests ./tests

RUN pip install --no-cache-dir ".[test]"

CMD ["python", "-m", "app.demo"]
