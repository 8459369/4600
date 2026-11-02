from flask import Flask, abort, flash, redirect, render_template, request, url_for
from werkzeug.wrappers import Response

from observatorio import servicos
from observatorio.servicos import ErroValidacao


def lista() -> str:
    return render_template("lista.html", organizacoes=servicos.listar_organizacoes())


def nova() -> str | Response | tuple[str, int]:
    erro = None
    if request.method == "POST":
        try:
            organizacao_id = servicos.registar_organizacao(
                request.form.get("nome", ""),
                request.form.get("nif", ""),
                request.form.get("tipo", type=int),
                request.form.get("setor", ""),
                request.form.get("freguesia", type=int),
            )
        except ErroValidacao as e:
            erro = str(e)
        else:
            # Redirecionar evita que "atualizar" a página repita o registo.
            return redirect(url_for("ficha", organizacao_id=organizacao_id))
    tipos, freguesias = servicos.opcoes_formulario()
    pagina = render_template(
        "formulario.html",
        erro=erro,
        campos=request.form,
        tipos=tipos,
        freguesias=freguesias,
        setores=servicos.SETORES,
    ) 
    return (pagina, 422) if erro else pagina


def ficha(organizacao_id: int) -> str:
    resultado = servicos.obter_ficha_com_recolhas(organizacao_id)
    if resultado is None:
        abort(404)
    organizacao, dominios, seeds = resultado
    return render_template(
        "ficha.html",
        organizacao=organizacao,
        dominios=dominios,
        seeds=seeds,
        setores=servicos.SETORES,
    )


def associar(organizacao_id: int) -> Response:
    try:
        associacao_nova = servicos.associar_dominio(organizacao_id, request.form.get("dominio", ""))
    except ErroValidacao as e:
        flash(str(e), "erro")
    else:
        flash(
            "Associaste o domínio." if associacao_nova else "O domínio já está associado.",
            "info",
        )
    return redirect(url_for("ficha", organizacao_id=organizacao_id))


def registar_rotas(app: Flask) -> None:
    app.add_url_rule("/", view_func=lista)
    app.add_url_rule("/organizacoes/nova", view_func=nova, methods=["GET", "POST"])
    app.add_url_rule("/organizacoes/<int:organizacao_id>", view_func=ficha)
    app.add_url_rule(
        "/organizacoes/<int:organizacao_id>/dominios", view_func=associar, methods=["POST"]
    )
