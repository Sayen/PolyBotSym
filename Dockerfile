FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY polybot.py .

ENV IS_DOCKER=true

CMD ["python", "polybot.py"]
