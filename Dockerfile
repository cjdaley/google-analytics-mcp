FROM python:3.11-slim

WORKDIR /app

COPY . .

RUN pip install --upgrade pip setuptools wheel
RUN pip install -e .

CMD ["python", "bridge.py"]
