import os

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-default-key")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///cortex.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JENKINS_URL = os.getenv("JENKINS_URL", "http://localhost:8080")
    JENKINS_USER = os.getenv("JENKINS_USER", "admin")
    JENKINS_TOKEN = os.getenv("JENKINS_TOKEN", "")
    PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
    TEE_MODE = os.getenv("TEE_MODE", "simulated")
    GITHUB_WEBHOOK_SECRET  = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    ALERTMANAGER_TOKEN     = os.getenv("ALERTMANAGER_TOKEN", "")
