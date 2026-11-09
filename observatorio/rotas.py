from flask import Flask, abort, flash, redirect, render_template, request, url_for
from werkzeug.wrappers import Response

from observatorio import servicos
from observatorio.servicos import ErroValidacao


def lista() -> str:
    pesquisa = request.args.get("q", "")
    tipo_id = request.args.get("tipo", type=int)
    freguesia_id = request.args.get("freguesia", type=int)
    setor = request.args.get("setor", "")
    tipos, freguesias = servicos.opcoes_formulario()
    return render_template(
        "lista.html",
        organizacoes=servicos.listar_organizacoes(
            pesquisa, tipo_id, freguesia_id, setor
        ),
        pesquisa=pesquisa,
        tipo_id=tipo_id,
        freguesia_id=freguesia_id,
        setor=setor,
        tipos=tipos,
        freguesias=freguesias,
        setores=servicos.SETORES,
        filtrado=bool(pesquisa or tipo_id or freguesia_id or setor),
    )


def _valores_formulario() -> tuple[str, str, int | None, str, int | None]:
    return (
        request.form.get("nome", ""),
        request.form.get("nif", ""),
        request.form.get("tipo", type=int),
        request.form.get("setor", ""),
        request.form.get("freguesia", type=int),
    )


def _formulario_organizacao(
    titulo: str, texto_botao: str, campos, erro: str | None
) -> str | tuple[str, int]:
    tipos, freguesias = servicos.opcoes_formulario()
    pagina = render_template(
        "formulario.html",
        titulo=titulo,
        texto_botao=texto_botao,
        erro=erro,
        campos=campos,
        tipos=tipos,
        freguesias=freguesias,
        setores=servicos.SETORES,
    )
    return (pagina, 422) if erro else pagina


def nova() -> str | Response | tuple[str, int]:
    if request.method == "POST":
        try:
            organizacao_id = servicos.registar_organizacao(*_valores_formulario())
        except ErroValidacao as e:
            return _formulario_organizacao(
                "Nova organização", "Regista", request.form, str(e)
            )
        # Redirecionar evita que "atualizar" a página repita o registo.
        return redirect(url_for("ficha", organizacao_id=organizacao_id))
    return _formulario_organizacao("Nova organização", "Regista", request.form, None)


def editar(organizacao_id: int) -> str | Response | tuple[str, int]:
    if request.method == "POST":
        try:
            servicos.editar_organizacao(organizacao_id, *_valores_formulario())
        except ErroValidacao as e:
            return _formulario_organizacao(
                "Editar organização", "Guarda", request.form, str(e)
            )
        flash("Organização atualizada.", "info")
        return redirect(url_for("ficha", organizacao_id=organizacao_id))
    organizacao = servicos.obter_organizacao(organizacao_id)
    if organizacao is None:
        abort(404)
    campos = {
        "nome": organizacao.nome,
        "nif": organizacao.nif or "",
        "tipo": str(organizacao.tipo_id),
        "setor": organizacao.setor,
        "freguesia": ""
        if organizacao.freguesia_id is None
        else str(organizacao.freguesia_id),
    }
    return _formulario_organizacao("Editar organização", "Guarda", campos, None)


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
        associacao_nova = servicos.associar_dominio(
            organizacao_id, request.form.get("dominio", "")
        )
    except ErroValidacao as e:
        flash(str(e), "erro")
    else:
        flash(
            "Associaste o domínio."
            if associacao_nova
            else "O domínio já está associado.",
            "info",
        )
    return redirect(url_for("ficha", organizacao_id=organizacao_id))


def habilitacao_seed(organizacao_id: int, seed_id: int) -> Response:
    habilitada = request.form.get("habilitada")
    if habilitada not in {"0", "1"}:
        abort(400)
    try:
        servicos.definir_habilitacao_seed(organizacao_id, seed_id, habilitada == "1")
    except ErroValidacao as e:
        flash(str(e), "erro")
    else:
        flash("Seed habilitada." if habilitada == "1" else "Seed desabilitada.", "info")
    return redirect(url_for("ficha", organizacao_id=organizacao_id))


def registar_rotas(app: Flask) -> None:
    app.add_url_rule("/", view_func=lista)
    app.add_url_rule("/organizacoes/nova", view_func=nova, methods=["GET", "POST"])
    app.add_url_rule("/organizacoes/<int:organizacao_id>", view_func=ficha)
    app.add_url_rule(
        "/organizacoes/<int:organizacao_id>/editar",
        view_func=editar,
        methods=["GET", "POST"],
    )
    app.add_url_rule(
        "/organizacoes/<int:organizacao_id>/dominios",
        view_func=associar,
        methods=["POST"],
    )
    app.add_url_rule(
        "/organizacoes/<int:organizacao_id>/seeds/<int:seed_id>/habilitacao",
        view_func=habilitacao_seed,
        methods=["POST"],
    )
