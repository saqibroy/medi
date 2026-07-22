FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade \
    setuptools==83.0.0 \
    wheel==0.47.0 \
  && python -m pip install --no-cache-dir -r backend/requirements.txt

COPY alembic.ini alembic.ini
COPY backend backend

EXPOSE 8000

CMD ["python", "-m", "backend.startup"]
