FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/tmp /app/logs

EXPOSE 8088

CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:8088", "app:app", "--timeout", "120"]
