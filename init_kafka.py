import os
import requests
import json
# Функции для получения данных о Kafka остаются без изменений
USERNAME = "your-username"
PASSWORD = "your-password"
DOMAIN_NAME = "your-domain-name"
IAM_URL = "https://iam.ru-moscow-1.hc.sbercloud.ru/v3"
DMS_URL = "https://dms.ru-moscow-1.hc.sbercloud.ru/v2"

project_name = os.getenv("PROJECT_NAME", "").strip()

if not project_name:
    raise ValueError("Ошибка: переменная окружения PROJECT_NAME не задана!")

print(f"project_name: {project_name}")  # Должно вывести корректное значение

kafka_password = os.getenv("AMAZME_KAFKA_PASSWORD", "").strip()
if not kafka_password:
    raise ValueError("Ошибка: переменная окружения kafka_password не задана!")

def get_auth_token(username, password, domain_name, iam_url, project_name):
    url = f"{iam_url}/auth/tokens"
    headers = {"Content-Type": "application/json"}
    body = {
        "auth": {
            "identity": {
                "methods": ["password"],
                "password": {
                    "user": {
                        "name": username,
                        "password": password,
                        "domain": {"name": domain_name}
                    }
                }
            },
            "scope": {
                "project": {
                    "name": project_name
                }
            }
        }   
    }
    response = requests.post(url, json=body, headers=headers)
    response.raise_for_status()
    return response.headers["X-Subject-Token"]

def get_project_id(token, iam_url, project_name):
    url = f"{iam_url}/projects"
    headers = {"Content-Type": "application/json", "X-Auth-Token": token}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    projects = response.json().get("projects", [])
    for project in projects:
        if project["name"] == project_name:
            return project["id"]
    raise ValueError(f"Проект '{project_name}' не найден.")

def get_available_kafka_services(token, project_id, dms_url):
    url = f"{dms_url}/{project_id}/instances"
    headers = {"Content-Type": "application/json", "X-Auth-Token": token}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

# Функция для поиска Kafka-инстанса по имени
def find_kafka_instance(kafka_services, desired_name):
    for instance in kafka_services.get("instances", []):
        if instance["name"] == desired_name:
            return instance
    return None

# Получаем токен
token = get_auth_token(USERNAME, PASSWORD, DOMAIN_NAME, IAM_URL, project_name)
print("token" + token)

project_id = get_project_id(token, IAM_URL, project_name)
print("project_id" + project_id)

kafka_services = get_available_kafka_services(token, project_id, DMS_URL)
# print("kafka_services:", json.dumps(kafka_services, indent=2, ensure_ascii=False))

if not kafka_services.get("instances"):
    print("Не найдено доступных Kafka сервисов!")
    exit(1)

desired_kafka_instance = os.getenv("AMAZME_KAFKA_INSTANCE_NAME", "").strip()
if not desired_kafka_instance:
    raise ValueError("Ошибка: переменная окружения AMAZME_KAFKA_INSTANCE_NAME не задана!")

kafka_instance = find_kafka_instance(kafka_services, desired_kafka_instance)
if not kafka_instance:
    raise ValueError(f"Ошибка: Kafka-инстанс с именем '{desired_kafka_instance}' не найден!")

kafka_cluster_name = kafka_instance["name"]
kafka_broker = kafka_instance["kafka_private_connect_address"]
kafka_username = kafka_instance["access_user"]
print("kafka_instance", json.dumps(kafka_instance, indent=2, ensure_ascii=False))
print("kafka_cluster_name=" + kafka_cluster_name)
print("kafka_broker=" + kafka_broker)
print("kafka_username=" + kafka_username)


# Записываем переменные в окружение и в файл
env_vars = {
    "AMAZME_KAFKA_URL": kafka_broker,
    "AMAZME_KAFKA_USER": kafka_username
}

with open("/app/kafka_env.sh", "w") as f:
    for key, value in env_vars.items():
        f.write(f"export {key}='{value}'\n")

print("Kafka environment variables saved!")
