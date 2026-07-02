"""WSGI entry point. On PythonAnywhere, set DATABASE_URL and SECRET_KEY as environment
variables in the web app's WSGI config (see DEPLOYMENT.md), then import this module."""
from app import app as application

if __name__ == "__main__":
    application.run()
