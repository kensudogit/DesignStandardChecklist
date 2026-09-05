FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 依存だけ先に入れて、アプリ変更でレイヤキャッシュが壊れないようにする。
# compose は PostgreSQL を使うため、任意依存の psycopg はこの構成では必須になる。
# anthropic も同時に入れておき、ANTHROPIC_API_KEY を渡すだけで使える状態にする。
COPY requirements.txt requirements-optional.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && pip install -r requirements-optional.txt

COPY app ./app
COPY pyproject.toml ./

# アップロードした標準書と SQLite の置き場。compose では volume を当てる。
RUN mkdir -p storage/uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
