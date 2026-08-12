"""Usuários do próprio Agente Oracle (login independente do Protheus — o
modelo de permissão do Protheus é interno das rotinas dele e não mapeia pros
módulos deste sistema). Time pequeno, sem tela de cadastro: usuários são
criados manualmente via `agente_oracle.tools.auth.cli` (script
`agente-oracle-criar-usuario`).

Segue o mesmo padrão de `tools/financeiro/historico.py`: tabela própria,
criada sozinha (`CREATE TABLE IF NOT EXISTS`) sempre no Postgres (estado do
sistema — ver `db/connection.py`), sem migração separada.
"""

import json
from datetime import UTC, datetime

import bcrypt

from agente_oracle.db.connection import DatabaseError, eh_erro_valor_duplicado, get_postgres_connection
from agente_oracle.tools.auth import eventos_seguranca

_COLUNAS = "id, usuario, senha_hash, nome, papeis, ativo, foto, tentativas_falhas, bloqueado, bloqueado_em"

# A partir de 3 tentativas de login erradas seguidas, a conta bloqueia até o
# time de TI (papel `desenvolvedor`) desbloquear manualmente — diferente do
# limite temporário de `server/auth/rate_limit.py` (5 tentativas em 3 min,
# em memória, se autolimpa sozinho), este é persistente e não expira.
LIMITE_TENTATIVAS_BLOQUEIO = 3

# Priorizando tamanho mínimo em vez de regra de composição (maiúscula +
# número + símbolo, etc.) — orientação atual do NIST 800-63B: regra de
# composição forçada tende a gerar senha previsível (ex: "Empresa123!") sem
# ganho real de segurança, enquanto tamanho mínimo generoso é mais eficaz e
# não pune quem já usa uma frase-senha longa.
TAMANHO_MINIMO_SENHA = 8

_tabela_garantida = False


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
    # ADD COLUMN IF NOT EXISTS é idempotente — instalações que já tinham a
    # tabela criada antes da foto existir ganham a coluna sozinhas aqui,
    # sem precisar de uma migração separada.
    cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS foto TEXT")
    cursor.execute(
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS tentativas_falhas INTEGER NOT NULL DEFAULT 0"
    )
    cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS bloqueado BOOLEAN NOT NULL DEFAULT FALSE")
    cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS bloqueado_em TIMESTAMPTZ")
    _tabela_garantida = True


def _linha_para_usuario(linha: tuple) -> dict:
    id_, usuario, senha_hash, nome, papeis, ativo, foto, tentativas_falhas, bloqueado, bloqueado_em = linha
    return {
        "id": id_,
        "usuario": usuario,
        "senha_hash": senha_hash,
        "nome": nome,
        "papeis": _carregar_papeis(papeis),
        "ativo": ativo,
        "foto": foto,
        "tentativas_falhas": tentativas_falhas,
        "bloqueado": bloqueado,
        "bloqueado_em": bloqueado_em,
    }


def _carregar_papeis(valor) -> list[str]:
    return json.loads(valor) if isinstance(valor, str) else valor


class UsuarioJaExiste(Exception):
    """Levantada quando `criar_usuario` recebe um `usuario` que já existe
    (constraint única) — traduzida pra uma resposta HTTP amigável na rota,
    em vez de deixar o erro cru do banco subir como 500."""


def alterar_senha(usuario: str, senha_atual: str, senha_nova: str) -> bool:
    """Autoatendimento: troca a senha do PRÓPRIO usuário, conferindo a senha
    atual antes. Devolve False se a senha atual não bater (usuário
    inexistente conta como não bater, mesma resposta pra não vazar
    informação)."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(f"SELECT {_COLUNAS} FROM usuarios WHERE usuario = :usuario", usuario=usuario)
        linha = cursor.fetchone()

        if linha is None:
            return False

        dados = _linha_para_usuario(linha)
        if not bcrypt.checkpw(senha_atual.encode("utf-8"), dados["senha_hash"].encode("utf-8")):
            return False

        novo_hash = bcrypt.hashpw(senha_nova.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        cursor.execute(
            "UPDATE usuarios SET senha_hash = :senha_hash WHERE usuario = :usuario",
            senha_hash=novo_hash,
            usuario=usuario,
        )

    return True


def atualizar_perfil(usuario: str, nome: str | None = None, foto: str | None = None) -> dict:
    """Autoatendimento: atualiza nome e/ou foto do PRÓPRIO usuário (só os
    campos informados). Devolve o perfil atualizado, sem o hash de senha."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        if nome is not None:
            cursor.execute(
                "UPDATE usuarios SET nome = :nome WHERE usuario = :usuario", nome=nome, usuario=usuario
            )
        if foto is not None:
            cursor.execute(
                "UPDATE usuarios SET foto = :foto WHERE usuario = :usuario", foto=foto, usuario=usuario
            )
        cursor.execute(f"SELECT {_COLUNAS} FROM usuarios WHERE usuario = :usuario", usuario=usuario)
        linha = cursor.fetchone()

    dados = _linha_para_usuario(linha)
    return {chave: valor for chave, valor in dados.items() if chave != "senha_hash"}


def autenticar(usuario: str, senha: str) -> dict | None:
    """Confere usuário/senha contra o hash salvo. Devolve os dados do usuário
    (sem o hash) em caso de sucesso, ou None se usuário não existir, estiver
    inativo, bloqueado, ou a senha não bater."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            f"SELECT {_COLUNAS} FROM usuarios WHERE usuario = :usuario AND ativo = TRUE AND bloqueado = FALSE",
            usuario=usuario,
        )
        linha = cursor.fetchone()
        if linha is None:
            return None

        dados = _linha_para_usuario(linha)
        if not bcrypt.checkpw(senha.encode("utf-8"), dados["senha_hash"].encode("utf-8")):
            return None

        if dados["tentativas_falhas"]:
            cursor.execute(
                "UPDATE usuarios SET tentativas_falhas = 0 WHERE usuario = :usuario", usuario=usuario
            )

    ocultos = ("senha_hash", "tentativas_falhas", "bloqueado_em")
    return {chave: valor for chave, valor in dados.items() if chave not in ocultos}


def criar_usuario(usuario: str, senha: str, nome: str, papeis: list[str]) -> dict:
    senha_hash = bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    try:
        with get_postgres_connection() as connection:
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
                criado_em=datetime.now(UTC),
            )
            linha = cursor.fetchone()
    except DatabaseError as erro:
        if eh_erro_valor_duplicado(erro):
            raise UsuarioJaExiste(f"Já existe um usuário com o login '{usuario}'.") from erro
        raise

    return _linha_para_usuario(linha)


def deletar_usuario(id_usuario: int) -> str | None:
    """Apaga um usuário. Devolve o login apagado (útil pra quem chama
    registrar o evento na trilha de auditoria com um nome legível, em vez
    de só o id), ou None se o id não existir."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute("DELETE FROM usuarios WHERE id = :id RETURNING usuario", id=id_usuario)
        linha = cursor.fetchone()

    return linha[0] if linha else None


def desbloquear_usuario(id_usuario: int) -> str | None:
    """Zera o bloqueio e o contador de tentativas de um usuário — ação do
    time de TI, disparada pela tela de administração. Devolve o login
    desbloqueado, ou None se o id não existir."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            """
            UPDATE usuarios SET bloqueado = FALSE, tentativas_falhas = 0, bloqueado_em = NULL
            WHERE id = :id
            RETURNING usuario
            """,
            id=id_usuario,
        )
        linha = cursor.fetchone()

    return linha[0] if linha else None


def esta_bloqueado(usuario: str) -> bool:
    """Consulta rápida e independente de senha — usada pela rota de login pra
    decidir a mensagem de erro antes mesmo de checar o rate limit."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute("SELECT bloqueado FROM usuarios WHERE usuario = :usuario", usuario=usuario)
        linha = cursor.fetchone()

    return bool(linha and linha[0])


def listar_usuarios() -> list[dict]:
    """Lista os usuários cadastrados (sem hash de senha nem foto — a tela de
    administração não mexe em foto de ninguém, só a própria pessoa mexe na
    dela via `/api/auth/perfil`), mais recentes primeiro."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(f"SELECT {_COLUNAS} FROM usuarios ORDER BY id DESC")
        linhas = cursor.fetchall()

    ocultos = ("senha_hash", "foto", "tentativas_falhas", "bloqueado_em")
    return [
        {chave: valor for chave, valor in _linha_para_usuario(linha).items() if chave not in ocultos}
        for linha in linhas
    ]


def registrar_tentativa_falha(usuario: str) -> bool:
    """Soma uma tentativa de login errada pro usuário (se existir) e bloqueia
    a conta ao atingir `LIMITE_TENTATIVAS_BLOQUEIO` — só o time de TI
    consegue desbloquear depois, via `desbloquear_usuario`. Devolve True se
    ESSA tentativa acabou de bloquear a conta."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            """
            UPDATE usuarios SET tentativas_falhas = tentativas_falhas + 1
            WHERE usuario = :usuario
            RETURNING tentativas_falhas
            """,
            usuario=usuario,
        )
        linha = cursor.fetchone()
        if linha is None:
            return False  # usuário não existe, nada a bloquear

        if linha[0] < LIMITE_TENTATIVAS_BLOQUEIO:
            return False

        cursor.execute(
            "UPDATE usuarios SET bloqueado = TRUE, bloqueado_em = :agora WHERE usuario = :usuario",
            agora=datetime.now(UTC),
            usuario=usuario,
        )

    eventos_seguranca.registrar("conta_bloqueada", usuario_afetado=usuario)
    return True


def senha_fraca(senha: str) -> str | None:
    """Devolve uma mensagem de erro se a senha não atender o mínimo de
    segurança, ou None se estiver ok — chamado tanto na criação de usuário
    quanto na troca de senha (`server/auth/rotas.py`)."""
    if len(senha) < TAMANHO_MINIMO_SENHA:
        return f"A senha precisa ter pelo menos {TAMANHO_MINIMO_SENHA} caracteres."
    return None


def usuario_esta_ativo_e_desbloqueado(id_usuario: int) -> bool:
    """Consulta rápida (por id, chave primária) chamada em toda requisição
    autenticada (`server/auth/dependencia.py:exigir_usuario`) — é o que
    permite revogar uma sessão NA HORA: se a conta for desativada ou
    bloqueada depois que o token já foi emitido, o token para de funcionar
    no request seguinte, em vez de continuar valendo até expirar (até
    `AUTH_TOKEN_HORAS` horas). Devolve False também se o id não existir mais
    (usuário apagado com uma sessão ainda aberta)."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute("SELECT ativo, bloqueado FROM usuarios WHERE id = :id", id=id_usuario)
        linha = cursor.fetchone()

    if linha is None:
        return False

    ativo, bloqueado = linha
    return bool(ativo) and not bool(bloqueado)
