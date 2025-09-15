import os
import time
import json
import requests
import psycopg2
import logging
from datetime import datetime
from requests_aws4auth import AWS4Auth

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Environment variables
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'litellm-users')
DB_USER = os.getenv('DB_USER', 'your_username')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'your_password')
YANDEX_FOLDER_ID = os.getenv('YANDEX_FOLDER_ID', 'your_folder_id')
YANDEX_ACCESS_KEY = os.getenv('YANDEX_ACCESS_KEY', 'your_access_key')
YANDEX_SECRET_KEY = os.getenv('YANDEX_SECRET_KEY', 'your_secret_key')
KEY_NAME = os.getenv('KEY_NAME', 'test')

# Yandex Monitoring API endpoint
METRICS_URL = 'https://monitoring.api.cloud.yandex.net/monitoring/v2/data/write'

def get_iam_token(access_key, secret_key):
    try:
        # Создаем объект AWS4Auth для подписи запроса
        auth = AWS4Auth(
            access_key,
            secret_key,
            'ru-central1',
            'iam',
            service='iam'
        )
        # Запрос к IAM API для получения токена
        response = requests.post(
            'https://iam.api.cloud.yandex.net/iam/v1/tokens',
            json={'yandexPassportOauthToken': ''},  # Пустой OAuth-токен, так как используем access_key
            auth=auth
        )
        response.raise_for_status()
        return response.json().get('iamToken')
    except Exception as e:
        logger.error(f"Error getting IAM token: {e}")
        return None

def get_spend_from_db():
    conn = None
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            sslmode='verify-full',
            target_session_attrs='read-write',
            sslrootcert='/root/.postgresql/root.crt'
        )
        cur = conn.cursor()
        query = """
        SELECT spend 
        FROM "LiteLLM_VerificationToken" 
        WHERE token = %s
        """
        cur.execute(query, (KEY_NAME,))
        result = cur.fetchone()
        cur.close()
        if result:
            spend = result[0]
            logger.info(f"Spend for token {KEY_NAME}: {spend}")
            return spend
        else:
            logger.warning(f"No record found for token: {KEY_NAME}")
            return None
    except Exception as e:
        logger.error(f"Database error: {e}")
        return None
    finally:
        if conn:
            conn.close()

def send_to_yandex_monitoring(spend):
    if spend is None:
        logger.warning("No spend value to send to Yandex Monitoring")
        return

    access_key = os.getenv('YANDEX_ACCESS_KEY')
    secret_key = os.getenv('YANDEX_SECRET_KEY')
    iam_token = get_iam_token(access_key, secret_key)
    if not iam_token:
        logger.error("Failed to get IAM token, skipping metrics send")
        return

    metrics_data = {
        "metrics": [
            {
                "name": "litellm_spend",
                "labels": {
                    "token": KEY_NAME
                },
                "value": float(spend),
                "ts": datetime.utcnow().isoformat() + "Z"
            }
        ]
    }

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {iam_token}'
    }

    params = {
        'folderId': YANDEX_FOLDER_ID,
        'service': 'custom'
    }

    try:
        response = requests.post(METRICS_URL, params=params, headers=headers, data=json.dumps(metrics_data))
        if response.status_code == 200:
            logger.info("Metrics sent successfully to Yandex Monitoring")
        else:
            logger.error(f"Error sending metrics: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"Request error: {e}")

def main():
    while True:
        spend = get_spend_from_db()
        if spend is not None:
            send_to_yandex_monitoring(spend)
        time.sleep(300)  # Sleep for 5 minutes (300 seconds)

if __name__ == "__main__":
    main()