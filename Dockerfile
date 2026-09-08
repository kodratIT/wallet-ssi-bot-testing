# Gunakan image Python resmi
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instal OS dependencies
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements dulu untuk leverage Docker cache
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy sisa aplikasi (holder_legacy.py di-ignore via .dockerignore jika perlu)
COPY . .

EXPOSE 5050

# Production: gunicorn dengan factory pattern
# Dev: python holder.py (ENABLE_AUTO_PRESENT=true untuk aktifkan job)
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5050", "app:create_app()"]
