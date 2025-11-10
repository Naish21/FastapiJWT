FROM python:3.13.1-slim-bookworm

COPY ./src /deploy/src
COPY ./requirements.txt /deploy
WORKDIR /deploy

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8080

CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "src.main:app", "--max-requests", "10000", "--bind", "0.0.0.0:8080"]
