FROM python:3.9-slim

# Установить системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    librdkafka-dev \
    python3-dev \
    make \
    curl \
    libssl-dev \
    libffi-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Установить зависимости Python
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir kafka-python prometheus_client confluent-kafka requests

# Копировать проект в контейнер
COPY . /app

# Установить рабочую директорию
WORKDIR /app

# Сделать start.sh исполняемым
RUN chmod +x /app/start.sh

# Запуск start.sh
CMD ["/bin/bash", "/app/start.sh"]