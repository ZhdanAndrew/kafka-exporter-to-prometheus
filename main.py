import os
import json
import logging
import ssl
import time
from ssl import SSLContext
from kafka import KafkaConsumer
from prometheus_client import Gauge, start_http_server, make_wsgi_app
from wsgiref.simple_server import make_server
from threading import Thread


# Чтение переменной окружения для уровня логирования
# logging_level = os.getenv("LOGGING_LEVEL", "CRITICAL").upper()
logging_level = "CRITICAL"
# Устанавливаем уровень логирования в зависимости от значения переменной окружения
level_dict = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}

# Если переменная окружения содержит неправильное значение, используем уровень INFO по умолчанию
logging.basicConfig(
    level=level_dict.get(logging_level, logging.CRITICAL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("KafkaMetricReader")

def _create_context(cert: str) -> SSLContext:
    """Create SSL context."""
    ssl.create_default_context()
    context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(cadata=cert)
    return context


def get_kafka_config(kafka_broker, kafka_username, kafka_password, kafka_cert_path="phy_ca.crt"):
    """Create and return Kafka configuration."""
    kafka_url = kafka_broker.strip().split(",")
    kafka_url = [url.strip() for url in kafka_url]

    config = {
        "bootstrap_servers": kafka_url,
        "user": kafka_username,
        "password": kafka_password,
        "mechanism": "PLAIN",
    }

    if os.path.exists(kafka_cert_path):
        with open(kafka_cert_path, 'r') as file:
            kafka_cert = file.read()
        config["context"] = _create_context(kafka_cert)
        config["security_protocol"] = "SASL_SSL"
    else:
        config["context"] = None
        config["security_protocol"] = "SASL_PLAINTEXT"

    return config

class KafkaMetricReader:
    def __init__(self, kafka_config, topic_name, group_id="metric-reader-group", timeout_ms=2000):
        """
        Initialize KafkaMetricReader.
        """
        self.topic_name = topic_name
        self.consumer = KafkaConsumer(
            topic_name,
            bootstrap_servers=kafka_config["bootstrap_servers"],
            group_id=group_id,
            auto_offset_reset="latest",
            enable_auto_commit=True,
            consumer_timeout_ms=timeout_ms,
            security_protocol=kafka_config["security_protocol"],
            sasl_mechanism=kafka_config["mechanism"],
            sasl_plain_username=kafka_config["user"],
            sasl_plain_password=kafka_config["password"],
            ssl_context=kafka_config["context"],
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            key_deserializer=lambda m: m.decode("utf-8") if m else None,
            fetch_max_bytes=104857600,
            max_partition_fetch_bytes=20485760,
            fetch_min_bytes=1,
            fetch_max_wait_ms=100,
        )
        self.metrics_registry = {}  # Словарь для хранения метрик
        logger.info(f"Connected to Kafka topic: {topic_name}")

    def get_or_create_metric(self, metric_name, unit, labels):
        """
        Получить или создать метрику Gauge.
        """
        key = (metric_name, tuple(labels.keys()))
        if key not in self.metrics_registry:
            self.metrics_registry[key] = Gauge(
                metric_name, 
                f"{metric_name} ({unit})", 
                labelnames=labels.keys()
            )
        return self.metrics_registry[key]

    def process_metrics(self, metrics_data):
        """Process metrics and expose them to Prometheus."""
        for metric in metrics_data:
            try:
                metric_name = metric["metric"]["metric_name"]
                dimensions = {dim["name"]: dim["value"] for dim in metric["metric"]["dimensions"]}
                value = metric["value"]
                unit = metric.get("unit", "unknown")

                topic_name_safe = self.topic_name.replace("-", "_")

                # Добавляем префикс к имени метрики
                prefixed_metric_name = f"cloud_kafka_exporter_{topic_name_safe}_{metric_name}"

                # Логируем имя метрики и её данные для дебага
                logger.debug(f"Processing metric: {prefixed_metric_name}, dimensions: {dimensions}, value: {value}, unit: {unit}")

                # Create or retrieve the metric
                labels = {"namespace": metric["metric"]["namespace"], **dimensions}
                gauge = self.get_or_create_metric(prefixed_metric_name, unit, labels)
                gauge.labels(**labels).set(value)

            except Exception as e:
                logger.error(f"Error processing metric: {e}. Metric data: {metric}")

    def read_metrics(self):
        """
        Read and process messages from the Kafka topic.
        """
        logger.info(f"Starting to read metrics from topic {self.topic_name}...")
        while True:
            try:
                for message in self.consumer:
                    metrics_data = message.value
                    logger.info(f"Received metrics data from topic {self.topic_name}")

                    if "metrics" in metrics_data:
                        self.process_metrics(metrics_data["metrics"])
                    else:
                        logger.warning("No 'metrics' key found in message")
            except Exception as e:
                logger.error(f"Error processing message from topic {self.topic_name}: {e}")
            time.sleep(1)

    def close(self):
        """Close the Kafka consumer."""
        if self.consumer:
            self.consumer.close()
            logger.info(f"Kafka consumer for topic {self.topic_name} closed")


def start_reader_for_topic(kafka_config, topic):
    """Start KafkaMetricReader for a specific topic."""
    try:
        reader = KafkaMetricReader(kafka_config, topic)
        logger.info(f"Successfully connected to Kafka topic: {topic}")
        try:
            reader.read_metrics()
        except KeyboardInterrupt:
            logger.info(f"Process for topic {topic} interrupted. Shutting down...")
        finally:
            reader.close()
    except Exception as e:
        logger.error(f"Failed to connect to Kafka topic {topic}. Error: {e}")



# Main execution
if __name__ == "__main__":
    # Получаем переменные окружения
    kafka_broker = os.getenv("AMAZME_KAFKA_URL", "").strip()
    if not kafka_broker:
        raise ValueError("Ошибка: переменная окружения kafka_broker не задана!")

    kafka_username = os.getenv("AMAZME_KAFKA_USER", "").strip()
    if not kafka_username:
        raise ValueError("Ошибка: переменная окружения kafka_username не задана!")

    kafka_password = os.getenv("AMAZME_KAFKA_PASSWORD", "").strip()
    if not kafka_password:
        raise ValueError("Ошибка: переменная окружения kafka_password не задана!")
    
    # Вызываем функцию с нужными параметрами
    kafka_config = get_kafka_config(kafka_broker, kafka_username, kafka_password)

    # Выводим или используем полученную конфигурацию
    print(kafka_config)

    # Список топиков для чтения
    topics = ["metrics-from-cloud-dms", "metrics-from-cloud-rds", "metrics-from-cloud-dcs", "metrics-from-cloud-dds"]

    # Стартуем Prometheus HTTP сервер
    app = make_wsgi_app()

    def handle_request(environ, start_response):
        # Логирование входящего запроса
        logger.info("Received metrics scrape request from Prometheus: %s", environ.get('REMOTE_ADDR'))
        return app(environ, start_response)

    http_server = make_server('', 8000, handle_request)
    Thread(target=http_server.serve_forever, daemon=True).start()
    logger.info("Prometheus HTTP server started on port 8000")

    # Запускаем чтение метрик в отдельных потоках
    threads = []
    for topic in topics:
        thread = Thread(target=start_reader_for_topic, args=(kafka_config, topic))
        thread.start()
        threads.append(thread)

    # Ждем завершения всех потоков
    for thread in threads:
        thread.join()
