import os
import time
import json
import requests
import psycopg2
import logging
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Вывод в stdout для docker logs
    ]
)
logger = logging.getLogger(__name__)

# Environment variables for PostgreSQL connection
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'litellm-users')
DB_USER = os.getenv('DB_USER', 'your_username')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'your_password')

# Environment variables for Yandex Cloud Monitoring
YANDEX_FOLDER_ID = os.getenv('YANDEX_FOLDER_ID', 'your_folder_id')

# The specific key_name to query
KEY_NAME = os.getenv('KEY_NAME', 'test')

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



def main():
    while True:
        spend = get_spend_from_db()
        if spend is not None:
            print(spend)
        time.sleep(300)  # Sleep for 5 minutes (300 seconds)

if __name__ == "__main__":
    main()