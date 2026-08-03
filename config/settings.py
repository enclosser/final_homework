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

# Имя модели, загруженной в LM Studio (см. .env.example)
LM_STUDIO_MODEL = env('LM_STUDIO_MODEL', default='')
