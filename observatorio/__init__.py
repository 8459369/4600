from flask import Flask

from observatorio.configuracao import chave_secreta, url_base_dados
from observatorio.rotas import registar_rotas


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["DATABASE_URL"] = url_base_dados()
    app.config["SECRET_KEY"] = chave_secreta()
    registar_rotas(app)
    return app
