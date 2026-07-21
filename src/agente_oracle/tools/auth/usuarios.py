"""Usuários do próprio Agente Oracle (login independente do Protheus — o
modelo de permissão do Protheus é interno das rotinas dele e não mapeia pros
módulos deste sistema). Time pequeno, sem tela de cadastro: usuários são
criados manualmente via `agente_oracle.tools.auth.cli` (script
`agente-oracle-criar-usuario`).

Segue o mesmo padrão de `tools/financeiro/historico.py`: tabela própria,
criada sozinha (`CREATE TABLE IF NOT EXISTS`) na mesma conexão relacional já
configurada em DB_BACKEND, sem migração separada.
"""

import json
from datetime import datetime, timezone

import bcrypt

from agente_oracle.db.connection import DatabaseError, eh_erro_valor_duplicado, get_connection

_COLUNAS = "id, usuario, senha_hash, nome, papeis, ativo"

_tabela_garantida = False


class UsuarioJaExiste(Exception):
    """Levantada quando `criar_usuario` recebe um `usuario` que já existe
    (constraint única) — traduzida pra uma resposta HTTP amigável na rota,
    em vez de deixar o erro cru do banco subir como 500."""


def _garantir_tabela(cursor) -> None:
    global _tabela_garantida
    if _tabela_garantida:
        return
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id BIGSERIAL PRIMARY KEY,
            usuario VARCHAR NOT NULL UNIQUE,
            senha_hash VARCHAR NOT NULL,
            nome VARCHAR NOT NULL,
            papeis JSONB NOT NULL,
            ativo BOOLEAN NOT NULL DEFAULT TRUE,
            criado_em TIMESTAMPTZ NOT NULL
        )
    """)
    _tabela_garantida = True


def _carregar_papeis(valor) -> list[str]:
    return json.loads(valor) if isinstance(valor, str) else valor


def _linha_para_usuario(linha: tuple) -> dict:
    id_, usuario, senha_hash, nome, papeis, ativo = linha
    return {
        "id": id_,
        "usuario": usuario,
        "senha_hash": senha_hash,
        "nome": nome,
        "papeis": _carregar_papeis(papeis),
        "ativo": ativo,
    }


def criar_usuario(usuario: str, senha: str, nome: str, papeis: list[str]) -> dict:
    senha_hash = bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            _garantir_tabela(cursor)
            cursor.execute(
                f"""
                INSERT INTO usuarios (usuario, senha_hash, nome, papeis, ativo, criado_em)
                VALUES (:usuario, :senha_hash, :nome, :papeis::jsonb, TRUE, :criado_em)
                RETURNING {_COLUNAS}
                """,
                usuario=usuario,
                senha_hash=senha_hash,
                nome=nome,
                papeis=json.dumps(papeis),
                criado_em=datetime.now(timezone.utc),
            )
            linha = cursor.fetchone()
    except DatabaseError as erro:
        if eh_erro_valor_duplicado(erro):
            raise UsuarioJaExiste(f"Já existe um usuário com o login '{usuario}'.") from erro
        raise

    return _linha_para_usuario(linha)


def listar_usuarios() -> list[dict]:
    """Lista os usuários cadastrados (sem o hash de senha), pra tela de
    administração — mais recentes primeiro."""
    with get_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(f"SELECT {_COLUNAS} FROM usuarios ORDER BY id DESC")
        linhas = cursor.fetchall()

    return [
        {chave: valor for chave, valor in _linha_para_usuario(linha).items() if chave != "senha_hash"}
        for linha in linhas
    ]


def autenticar(usuario: str, senha: str) -> dict | None:
    """Confere usuário/senha contra o hash salvo. Devolve os dados do usuário
    (sem o hash) em caso de sucesso, ou None se usuário não existir, estiver
    inativo, ou a senha não bater."""
    with get_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            f"SELECT {_COLUNAS} FROM usuarios WHERE usuario = :usuario AND ativo = TRUE",
            usuario=usuario,
        )
        linha = cursor.fetchone()

    if linha is None:
        return None

    dados = _linha_para_usuario(linha)
    if not bcrypt.checkpw(senha.encode("utf-8"), dados["senha_hash"].encode("utf-8")):
        return None

    return {chave: valor for chave, valor in dados.items() if chave != "senha_hash"}
