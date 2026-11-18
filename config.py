"""Configuración de la aplicación. Los valores sensibles se leen del archivo .env."""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Zona horaria y sesión
    ZONA_HORARIA = "America/La_Paz"
    HORAS_SESION = 8
    PERMANENT_SESSION_LIFETIME = timedelta(hours=HORAS_SESION)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "0") == "1"
    REMEMBER_COOKIE_DURATION = timedelta(seconds=0)

    # Bloqueo por intentos fallidos
    MAX_INTENTOS = 5
    MINUTOS_BLOQUEO = 15

    # Umbrales de alertas (días)
    DIAS_POR_VENCER = 3
    DIAS_SEGUIMIENTO = 7
    DIAS_SIN_ACTUALIZAR = 7
    DIAS_CRITICO = 15
    META_CUMPLIMIENTO = 80  # % de tareas concluidas a tiempo (marca del velocímetro en Gráficos)

    # Archivos
    MAX_MB_ADJUNTO = 10
    MAX_CONTENT_LENGTH = (MAX_MB_ADJUNTO + 1) * 1024 * 1024
    EXTENSIONES_ADJUNTO = {
        "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "odp", "rtf", "txt", "csv",
        "jpg", "jpeg", "png", "gif", "webp", "zip", "rar", "7z", "msg", "eml",
    }
    TAREAS_POR_PAGINA = 50
    STORAGE_DIR = Path(os.getenv("STORAGE_DIR", BASE_DIR / "storage"))
    SOFFICE_PATH = os.getenv("SOFFICE_PATH", "soffice")
    SOFFICE_TIMEOUT = 60

    WTF_CSRF_TIME_LIMIT = None  # el token vive lo que dura la sesión


class DesarrolloConfig(Config):
    DEBUG = True


class ProduccionConfig(Config):
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "1") == "1"


class PruebasConfig(Config):
    TESTING = True
    SECRET_KEY = "clave-de-pruebas"
    SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL", "sqlite://")
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False


CONFIGURACIONES = {
    "desarrollo": DesarrolloConfig,
    "produccion": ProduccionConfig,
    "pruebas": PruebasConfig,
}
