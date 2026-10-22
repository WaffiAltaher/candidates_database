FROM python:3.11-slim

WORKDIR /app

COPY container/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY candidates/ ./candidates/
COPY container/main.py .

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

USER 10001:10001

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
