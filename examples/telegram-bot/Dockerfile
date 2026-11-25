FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

RUN useradd --create-home --uid 10001 bot && mkdir /data && chown bot /data
USER bot
ENV DB_PATH=/data/demo.sqlite3 PORT=8080
VOLUME /data
EXPOSE 8080

CMD ["python", "bot.py"]
