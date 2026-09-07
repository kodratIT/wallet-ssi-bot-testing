# Gunakan image Python resmi
FROM python:3.11-slim

# Set environment variable agar Python tidak buffering output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instal OS dependencies (opsional, tergantung kebutuhan)
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Set workdir
WORKDIR /app

# Copy file aplikasi
COPY . .

# Install dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Expose port yang digunakan Flask
EXPOSE 5050

# Jalankan aplikasi
CMD ["python", "holder.py"]
