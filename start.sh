#!/bin/bash
set -e  # Останавливать выполнение при ошибке

echo "Запуск скрипта инициализации Kafka..."
python /app/init_kafka.py

# Загружаем переменные окружения
if [ -f "/app/kafka_env.sh" ]; then
    echo "Загружаем переменные окружения из kafka_env.sh"
    source /app/kafka_env.sh
fi

echo "Запуск основного приложения..."
exec python /app/main.py
