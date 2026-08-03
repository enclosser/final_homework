from pathlib import Path

import environ

# Корень проекта (каталог, в котором лежит .env)
BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(DEBUG=(bool, False),)

# Явно загружаем .env из корня проекта
ENV_FILE = BASE_DIR / '.env'
if ENV_FILE.exists():
    env.read_env(ENV_FILE)

DEBUG = env('DEBUG')

# LM Studio — локальная LLM
LM_STUDIO_HOST = env('LM_STUDIO_HOST', default='http://localhost:1234/v1')
LM_STUDIO_API_KEY = env('LM_STUDIO_API_KEY', default='lm-studio')

# Тяжёлая и лёгкая модели (в учебном проекте — одна и та же, см. .env.example)
LM_STUDIO_MODEL_HEAVY = env('LM_STUDIO_MODEL_HEAVY', default='')
LM_STUDIO_MODEL_LIGHT = env('LM_STUDIO_MODEL_LIGHT', default='')

# Embedding-модель для векторной памяти (RAG)
EMBEDDING_MODEL = env('EMBEDDING_MODEL', default='text-embedding-nomic-embed-text-v1.5')

# Каталог векторной базы данных Chroma (создаётся при первом запуске)
CHROMA_DIR = BASE_DIR / 'data' / 'chroma'
# Имя коллекции в Chroma (база знаний для RAG)
CHROMA_COLLECTION = env('CHROMA_COLLECTION', default='support_kb')

# Файл пошагового лога агентного цикла (data/trace.jsonl)
TRACE_FILE = BASE_DIR / 'data' / env('TRACE_FILE_NAME', default='trace.jsonl')

# Сервисы-эмуляторы (см. .env.example)
LDAP_SERVICE_HOST = env('LDAP_SERVICE_HOST', default='localhost')
LDAP_SERVICE_PORT = env('LDAP_SERVICE_PORT', default='8101')
EXCHANGE_SERVICE_HOST = env('EXCHANGE_SERVICE_HOST', default='localhost')
EXCHANGE_SERVICE_PORT = env('EXCHANGE_SERVICE_PORT', default='8102')
ONEC_SERVICE_HOST = env('ONEC_SERVICE_HOST', default='localhost')
ONEC_SERVICE_PORT = env('ONEC_SERVICE_PORT', default='8103')

LDAP_BASE_URL = f'http://{LDAP_SERVICE_HOST}:{LDAP_SERVICE_PORT}'
EXCHANGE_BASE_URL = f'http://{EXCHANGE_SERVICE_HOST}:{EXCHANGE_SERVICE_PORT}'
ONEC_BASE_URL = f'http://{ONEC_SERVICE_HOST}:{ONEC_SERVICE_PORT}'
