"""Leitura só-de-consulta do controle de login/usuário do próprio Protheus
(`SYS_USR_LOGIN`/`SYS_USR`, banco separado do STAGE/BI) — insumo real pro
agente de detecção de segurança (`agent/ti/deteccao_seguranca.py`) sobre
QUEM logou no ERP, de que IP/máquina, e quantas tentativas de bloqueio
teve. Sem essa fonte, a detecção só enxergava o próprio login do
AgenteOracle (`tools/auth/eventos_seguranca.py`), nunca o do Protheus.

REGRA DE SEGURANÇA (inegociável): esse banco é gerenciado por outro time e
não pode ser alterado nem apagado por este sistema — só `SELECT`, sempre
com lista explícita de coluna (nunca `SELECT *`). Em especial,
`SYS_USR.USR_PSWMD5` (hash de senha) NUNCA é lido aqui, mesmo a tabela
tendo outras colunas úteis — evita qualquer risco de expor credencial.

Best-effort de propósito: sem `PROTHEUS_DSN` configurado (padrão), ou se a
conexão/consulta falhar por qualquer motivo, as funções aqui devolvem
lista vazia em vez de erro — a detecção de segurança continua funcionando
só com o que tiver disponível, mesmo espírito de
`agent/auditoria/analise.py` com o Ollama fora do ar."""

from datetime import UTC, datetime, timedelta

from agente_oracle.config import settings
from agente_oracle.db.connection import DatabaseError, get_protheus_connection, protheus_configurado


def logins_recentes(dias: int) -> list[dict]:
    """Um registro por login bem-sucedido no Protheus nos últimos `dias`
    dias — usuário, data/hora, IP e máquina de origem. Colunas de texto do
    Protheus vêm com espaço de preenchimento fixo, por isso o `.strip()`
    em tudo."""
    if not protheus_configurado():
        return []

    desde = (datetime.now(UTC) - timedelta(days=dias)).strftime("%Y%m%d")
    try:
        with get_protheus_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT USR_USERSOLOGON, USR_DTLOGON, USR_HRLOGON, USR_IPLOGON, USR_CNLOGON
                FROM {settings.protheus_schema}.SYS_USR_LOGIN
                WHERE D_E_L_E_T_ = ' ' AND USR_DTLOGON >= :desde
                """,
                desde=desde,
            )
            linhas = cursor.fetchall()
    except DatabaseError:
        return []

    return [
        {
            "usuario": (usuario or "").strip(),
            "data": (data or "").strip(),
            "hora": (hora or "").strip(),
            "ip": (ip or "").strip(),
            "maquina": (maquina or "").strip(),
        }
        for usuario, data, hora, ip, maquina in linhas
    ]


def tentativas_bloqueio_recentes() -> list[dict]:
    """Estado de bloqueio por tentativa de login errada, por usuário — só
    as 3 colunas necessárias de `SYS_USR`. NUNCA `USR_PSWMD5` nem qualquer
    outra coluna de credencial, mesmo que pareça conveniente no futuro."""
    if not protheus_configurado():
        return []

    try:
        with get_protheus_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(f"""
                SELECT USR_CODIGO, USR_MSBLQL, USR_QTDTENTBLQ
                FROM {settings.protheus_schema}.SYS_USR
                WHERE D_E_L_E_T_ = ' '
            """)
            linhas = cursor.fetchall()
    except DatabaseError:
        return []

    return [
        {
            "usuario": (codigo or "").strip(),
            "bloqueado": (bloqueado or "").strip() == "1",
            "tentativas": tentativas or 0,
        }
        for codigo, bloqueado, tentativas in linhas
    ]
