FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY main.py /app/main.py
COPY kube_pod_alerts /app/kube_pod_alerts

RUN useradd --create-home appuser
USER appuser

CMD ["python", "main.py"]
