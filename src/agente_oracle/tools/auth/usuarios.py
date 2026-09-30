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
from agente_oracle.tools.auth import cores_ambiente, eventos_seguranca, layout_dashboard, restricoes_filial

_COLUNAS = (
    "id, usuario, senha_hash, nome, papeis, ativo, foto, tentativas_falhas, bloqueado, bloqueado_em, "
    "tecnico_glpi_id, area_ti, email"
)

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

_INDICE_EMAIL_UNICO = "usuarios_email_unico"

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
    # Vínculo opcional com um técnico real do GLPI (`tools/ti/glpi.py::
    # buscar_tecnicos_disponiveis`/`buscar_area_do_tecnico`) — só
    # preenchido pra quem de fato atende chamado; `area_ti` é resolvida ao
    # vivo contra o GLPI na hora do cadastro (rota `usuarios_route`), não
    # recalculada depois. `tools/ti/tecnicos.py` lê os dois pra montar o
    # roster de técnicos, no lugar da tupla fixa que existia antes.
    cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS tecnico_glpi_id VARCHAR")
    cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS area_ti VARCHAR")
    # E-mail corporativo — obrigatório só quando um técnico do GLPI é
    # vinculado (`usuarios_route` confere contra o e-mail real da pessoa no
    # GLPI antes de gravar), por isso a coluna em si continua opcional aqui.
    cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS email VARCHAR")
    # Único quando preenchido (`WHERE email IS NOT NULL` — vários `NULL` não
    # violam unicidade no Postgres, mas seríamos explícitos mesmo assim) —
    # passou a valer como segundo jeito de logar (`resolver_login`,
    # 2026-09-28), então precisa apontar pra UMA conta só, sem ambiguidade.
    # `LOWER(...)` porque e-mail não diferencia maiúscula de minúscula.
    cursor.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {_INDICE_EMAIL_UNICO} "
        "ON usuarios (LOWER(email)) WHERE email IS NOT NULL"
    )
    _tabela_garantida = True


def _linha_para_usuario(linha: tuple) -> dict:
    (
        id_,
        usuario,
        senha_hash,
        nome,
        papeis,
        ativo,
        foto,
        tentativas_falhas,
        bloqueado,
        bloqueado_em,
        tecnico_glpi_id,
        area_ti,
        email,
    ) = linha
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
        "tecnico_glpi_id": tecnico_glpi_id,
        "area_ti": area_ti,
        "email": email,
    }


def _carregar_papeis(valor) -> list[str]:
    return json.loads(valor) if isinstance(valor, str) else valor


class UsuarioJaExiste(Exception):
    """Levantada quando `criar_usuario` recebe um `usuario` que já existe
    (constraint única) — traduzida pra uma resposta HTTP amigável na rota,
    em vez de deixar o erro cru do banco subir como 500."""


class EmailJaUsado(Exception):
    """Levantada quando `criar_usuario`/`atualizar_usuario` recebem um
    `email` que já está em uso por OUTRA conta (índice único de
    `_INDICE_EMAIL_UNICO`) — duas contas com o mesmo e-mail deixariam
    `resolver_login` ambíguo (login por e-mail não saberia qual delas
    escolher)."""


def _email_duplicado(erro: Exception) -> bool:
    return getattr(getattr(erro, "diag", None), "constraint_name", None) == _INDICE_EMAIL_UNICO


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


def criar_usuario(
    usuario: str,
    senha: str,
    nome: str,
    papeis: list[str],
    tecnico_glpi_id: str | None = None,
    area_ti: str | None = None,
    email: str | None = None,
) -> dict:
    """`tecnico_glpi_id`/`area_ti`/`email` só gravam o que recebem — este
    módulo não conhece GLPI de propósito (evita `tools/auth` depender de
    `tools/ti`). É `usuarios_route` (`server/auth/rotas.py`) quem resolve
    `area_ti` e confere `email` contra o GLPI antes de chamar isto aqui."""
    senha_hash = bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    try:
        with get_postgres_connection() as connection:
            cursor = connection.cursor()
            _garantir_tabela(cursor)
            cursor.execute(
                f"""
                INSERT INTO usuarios
                    (usuario, senha_hash, nome, papeis, ativo, criado_em, tecnico_glpi_id, area_ti, email)
                VALUES
                    (:usuario, :senha_hash, :nome, :papeis::jsonb, TRUE, :criado_em, :tecnico_glpi_id,
                     :area_ti, :email)
                RETURNING {_COLUNAS}
                """,
                usuario=usuario,
                senha_hash=senha_hash,
                nome=nome,
                papeis=json.dumps(papeis),
                criado_em=datetime.now(UTC),
                tecnico_glpi_id=tecnico_glpi_id,
                area_ti=area_ti,
                email=email,
            )
            linha = cursor.fetchone()
    except DatabaseError as erro:
        # Checa o e-mail primeiro: `eh_erro_valor_duplicado` é genérico (só
        # olha o sqlstate 23505), bateria também pro índice de e-mail.
        if _email_duplicado(erro):
            raise EmailJaUsado(f"Já existe uma conta usando o e-mail '{email}'.") from erro
        if eh_erro_valor_duplicado(erro):
            raise UsuarioJaExiste(f"Já existe um usuário com o login '{usuario}'.") from erro
        raise

    return _linha_para_usuario(linha)


def atualizar_usuario(
    id_usuario: int,
    nome: str,
    papeis: list[str],
    tecnico_glpi_id: str | None,
    area_ti: str | None,
    email: str | None,
    senha: str | None = None,
) -> dict | None:
    """Atualiza os dados administráveis de um usuário já existente — mesmos
    campos de `criar_usuario` (menos o login, que não muda depois de criado:
    é usado como referência em sessão/trilha de auditoria, renomear
    quebraria as duas). `senha` é OPCIONAL: `None`/vazio mantém a senha
    atual, só troca quando quem edita digita uma nova. Devolve o usuário
    atualizado, ou `None` se o id não existir."""
    campos_sql = [
        "nome = :nome",
        "papeis = :papeis::jsonb",
        "tecnico_glpi_id = :tecnico_glpi_id",
        "area_ti = :area_ti",
        "email = :email",
    ]
    binds = {
        "id": id_usuario,
        "nome": nome,
        "papeis": json.dumps(papeis),
        "tecnico_glpi_id": tecnico_glpi_id,
        "area_ti": area_ti,
        "email": email,
    }
    if senha:
        campos_sql.append("senha_hash = :senha_hash")
        binds["senha_hash"] = bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    try:
        with get_postgres_connection() as connection:
            cursor = connection.cursor()
            _garantir_tabela(cursor)
            cursor.execute(
                f"UPDATE usuarios SET {', '.join(campos_sql)} WHERE id = :id RETURNING {_COLUNAS}",
                **binds,
            )
            linha = cursor.fetchone()
    except DatabaseError as erro:
        if _email_duplicado(erro):
            raise EmailJaUsado(f"Já existe uma conta usando o e-mail '{email}'.") from erro
        raise

    return _linha_para_usuario(linha) if linha else None


def resolver_login(entrada: str) -> str | None:
    """Devolve o LOGIN correspondente a `entrada`, aceitando tanto o
    próprio login quanto o e-mail cadastrado (pedido do usuário,
    2026-09-28: entrar com qualquer um dos dois) — `None` se não bater com
    nenhuma conta. Comparação por e-mail é case-insensitive (mesmo motivo
    do índice único em `_garantir_tabela`); login continua exato, como
    sempre foi. Só resolve QUAL conta é — não confere senha nem
    ativo/bloqueado, isso continua em `autenticar`/`esta_bloqueado`,
    chamados depois com o login já resolvido."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            "SELECT usuario FROM usuarios WHERE usuario = :entrada OR LOWER(email) = LOWER(:entrada)",
            entrada=entrada,
        )
        linha = cursor.fetchone()

    return linha[0] if linha else None


def listar_tecnicos_ti() -> list[dict]:
    """Fonte de dado do roster de técnicos (`tools/ti/tecnicos.py`) — todo
    usuário ativo com um técnico do GLPI vinculado no cadastro (ver
    `criar_usuario`). Substitui a tupla fixa que existia antes; cresce
    junto com o cadastro de usuário, sem precisar editar código.
    `ORDER BY id` dá uma ordem estável (quem cadastrou primeiro) — mesmo
    papel que a ordem literal da tupla fixa tinha, usado por
    `escolher_tecnico` pra desempatar carga igual."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute(
            "SELECT usuario, nome, tecnico_glpi_id, area_ti FROM usuarios "
            "WHERE tecnico_glpi_id IS NOT NULL AND ativo = TRUE "
            "ORDER BY id ASC"
        )
        linhas = cursor.fetchall()

    return [
        {"usuario": usuario, "nome": nome, "tecnico_glpi_id": tecnico_glpi_id, "area_ti": area_ti}
        for usuario, nome, tecnico_glpi_id, area_ti in linhas
    ]


def deletar_usuario(id_usuario: int) -> str | None:
    """Apaga um usuário. Devolve o login apagado (útil pra quem chama
    registrar o evento na trilha de auditoria com um nome legível, em vez
    de só o id), ou None se o id não existir."""
    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        _garantir_tabela(cursor)
        cursor.execute("DELETE FROM usuarios WHERE id = :id RETURNING usuario", id=id_usuario)
        linha = cursor.fetchone()

    if linha:
        restricoes_filial.remover_usuario(id_usuario)
        layout_dashboard.remover_usuario(id_usuario)
        cores_ambiente.remover_usuario(id_usuario)
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
