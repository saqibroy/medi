FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HOME=/tmp
ENV XDG_CACHE_HOME=/tmp/.cache

WORKDIR /app

RUN groupadd --gid 10001 medi \
  && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin medi

COPY backend/requirements.txt backend/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade \
    setuptools==83.0.0 \
    wheel==0.47.0 \
  && python -m pip install --no-cache-dir -r backend/requirements.txt

COPY --chown=10001:10001 alembic.ini alembic.ini
COPY --chown=10001:10001 backend backend

USER 10001:10001

EXPOSE 8000

CMD ["python", "-m", "backend.startup"]
