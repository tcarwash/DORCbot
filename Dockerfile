FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY dorcbot/requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY dorcbot/ ./dorcbot/
RUN useradd --create-home --uid 10001 bot \
    && mkdir -p /data \
    && chown bot:bot /data \
    && chown -R bot:bot /app

USER bot
CMD ["python", "-m", "dorcbot.dorcbot"]
