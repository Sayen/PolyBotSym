FROM python:3.9-slim

WORKDIR /app

# Install tzdata for timezone support
RUN apt-get update && apt-get install -y tzdata && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY polybot.py .

ENV IS_DOCKER=true

CMD ["python", "polybot.py"]
