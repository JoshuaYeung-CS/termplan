FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PORT=7860

# Hugging Face Spaces runs containers as uid 1000; Render and others are fine with it too.
RUN useradd -m -u 1000 app
WORKDIR /home/app/termplan

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=app:app termplan ./termplan
COPY --chown=app:app examples ./examples
USER app

EXPOSE 7860
CMD ["sh", "-c", "uvicorn termplan.app:app --host 0.0.0.0 --port ${PORT:-7860} --proxy-headers --forwarded-allow-ips='*'"]
