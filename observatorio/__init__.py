from flask import Flask

from observatorio.configuracao import url_base_dados


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["DATABASE_URL"] = url_base_dados()
    return app
