FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY setup/ /app/setup/
# Dockerfile
COPY product_model.h5 /app/product_model.h5
COPY model_classes.json /app/model_classes.json

CMD ["python", "app.py"]
