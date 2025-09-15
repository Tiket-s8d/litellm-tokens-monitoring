import os
import time
import json
import requests
import psycopg2
import logging
from datetime import datetime
import jwt
from yandexcloud import SDK
from yandex.cloud.iam.v1.iam_token_service_pb2 import CreateIamTokenRequest
from yandex.cloud.iam.v1.iam_token_service_pb2_grpc import IamTokenServiceStub

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
KEY_NAME = os.getenv('KEY_NAME', 'test')

# Yandex Monitoring API endpoint
METRICS_URL = 'https://monitoring.api.cloud.yandex.net/monitoring/v2/data/write'

def create_jwt():
    try:
        with open('/app/key.json') as f:
            key_data = json.load(f)
        now = int(time.time())
        payload = {
            'aud': 'https://iam.api.cloud.yandex.net/iam/v1/tokens',
            'iss': key_data['service_account_id'],
            'iat': now,
            'exp': now + 3600
        }
        encoded_jwt = jwt.encode(
            payload,
            key_data['private_key'],
            algorithm='PS256',
            headers={'kid': key_data['id']}
        )
        return encoded_jwt
    except Exception as e:
        logger.error(f"Error creating JWT: {e}")
        return None

def get_iam_token():
    try:
        with open('/app/key.json') as f:
            key_data = json.load(f)
        sa_key = {
            "id": key_data['id'],
            "service_account_id": key_data['service_account_id'],
            "private_key": key_data['private_key']
        }
        jwt = create_jwt()
        if not jwt:
            return None
        sdk = SDK(service_account_key=sa_key)
        iam_service = sdk.client(IamTokenServiceStub)
        iam_token = iam_service.Create(CreateIamTokenRequest(jwt=jwt))
        logger.info("IAM token obtained successfully")
        return iam_token.iam_token
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

    iam_token = get_iam_token()
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