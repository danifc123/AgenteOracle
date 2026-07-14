--------------------------------------------------------------------------------
-- MODELAGEM DE BANCO DE DADOS - DEPARTAMENTO FINANCEIRO (AMBIENTE DE TESTE)
-- SGBD: PostgreSQL — tradução de consultas.sql (Oracle), para testar o agente
-- localmente sem tocar no banco de produção da empresa.
--
-- Tabelas:
--   1. CONTAS_BANCARIAS       -> contas/caixas da empresa
--   2. CATEGORIAS_FINANCEIRAS -> categorias de receita/despesa
--   3. FORNECEDORES_CLIENTES  -> entidades externas (fornecedores e clientes)
--   4. TRANSACOES             -> lançamentos financeiros (entradas/saídas)
--   5. FATURAS                -> faturas/documentos vinculados às transações
--   6. CENTROS_CUSTO          -> áreas/departamentos internos que geram gasto
--   7. ORCAMENTOS             -> valor previsto por categoria/mês (orçado x realizado)
--------------------------------------------------------------------------------

--------------------------------------------------------------------------------
-- 0. LIMPEZA (permite reexecutar o script em ambiente de teste)
--------------------------------------------------------------------------------
DROP TABLE IF EXISTS ORCAMENTOS, FATURAS, TRANSACOES, CENTROS_CUSTO,
    FORNECEDORES_CLIENTES, CATEGORIAS_FINANCEIRAS, CONTAS_BANCARIAS CASCADE;

--------------------------------------------------------------------------------
-- 1. CONTAS_BANCARIAS
--------------------------------------------------------------------------------
CREATE TABLE CONTAS_BANCARIAS (
    ID_CONTA        INTEGER         GENERATED ALWAYS AS IDENTITY (START WITH 1) PRIMARY KEY,
    NOME_CONTA      VARCHAR(100)    NOT NULL,
    BANCO           VARCHAR(50)     NOT NULL,
    AGENCIA         VARCHAR(10),
    NUMERO_CONTA    VARCHAR(20),
    TIPO_CONTA      VARCHAR(20)     NOT NULL,
    SALDO_ATUAL     NUMERIC(15,2)   DEFAULT 0 NOT NULL,
    DATA_ABERTURA   DATE            NOT NULL,
    CONSTRAINT CK_CONTAS_TIPO CHECK (TIPO_CONTA IN ('CORRENTE','POUPANCA','INVESTIMENTO'))
);

--------------------------------------------------------------------------------
-- 2. CATEGORIAS_FINANCEIRAS
--------------------------------------------------------------------------------
CREATE TABLE CATEGORIAS_FINANCEIRAS (
    ID_CATEGORIA    INTEGER         GENERATED ALWAYS AS IDENTITY (START WITH 1) PRIMARY KEY,
    NOME_CATEGORIA  VARCHAR(60)     NOT NULL,
    TIPO_CATEGORIA  VARCHAR(10)     NOT NULL,
    DESCRICAO       VARCHAR(200),
    CONSTRAINT CK_CATEGORIA_TIPO CHECK (TIPO_CATEGORIA IN ('RECEITA','DESPESA'))
);

--------------------------------------------------------------------------------
-- 3. FORNECEDORES_CLIENTES
--------------------------------------------------------------------------------
CREATE TABLE FORNECEDORES_CLIENTES (
    ID_ENTIDADE     INTEGER         GENERATED ALWAYS AS IDENTITY (START WITH 1) PRIMARY KEY,
    NOME            VARCHAR(100)    NOT NULL,
    TIPO_ENTIDADE   VARCHAR(15)     NOT NULL,
    CNPJ_CPF        VARCHAR(20),
    EMAIL           VARCHAR(100),
    TELEFONE        VARCHAR(20),
    CONSTRAINT CK_ENTIDADE_TIPO CHECK (TIPO_ENTIDADE IN ('FORNECEDOR','CLIENTE'))
);

--------------------------------------------------------------------------------
-- 4. TRANSACOES
--------------------------------------------------------------------------------
CREATE TABLE TRANSACOES (
    ID_TRANSACAO    INTEGER         GENERATED ALWAYS AS IDENTITY (START WITH 1) PRIMARY KEY,
    ID_CONTA        INTEGER         NOT NULL,
    ID_CATEGORIA    INTEGER         NOT NULL,
    ID_ENTIDADE     INTEGER,
    TIPO_TRANSACAO  VARCHAR(10)     NOT NULL,
    DESCRICAO       VARCHAR(200)    NOT NULL,
    VALOR           NUMERIC(15,2)   NOT NULL,
    DATA_TRANSACAO  DATE            NOT NULL,
    STATUS_TRANSACAO VARCHAR(15)    DEFAULT 'PENDENTE' NOT NULL,
    CONSTRAINT CK_TRANSACAO_TIPO CHECK (TIPO_TRANSACAO IN ('ENTRADA','SAIDA')),
    CONSTRAINT CK_TRANSACAO_STATUS CHECK (STATUS_TRANSACAO IN ('PAGO','PENDENTE','CANCELADO')),
    CONSTRAINT CK_TRANSACAO_VALOR CHECK (VALOR > 0),
    CONSTRAINT FK_TRANSACAO_CONTA FOREIGN KEY (ID_CONTA) REFERENCES CONTAS_BANCARIAS (ID_CONTA),
    CONSTRAINT FK_TRANSACAO_CATEGORIA FOREIGN KEY (ID_CATEGORIA) REFERENCES CATEGORIAS_FINANCEIRAS (ID_CATEGORIA),
    CONSTRAINT FK_TRANSACAO_ENTIDADE FOREIGN KEY (ID_ENTIDADE) REFERENCES FORNECEDORES_CLIENTES (ID_ENTIDADE)
);

--------------------------------------------------------------------------------
-- 5. FATURAS
--------------------------------------------------------------------------------
CREATE TABLE FATURAS (
    ID_FATURA       INTEGER         GENERATED ALWAYS AS IDENTITY (START WITH 1) PRIMARY KEY,
    ID_TRANSACAO    INTEGER         NOT NULL,
    NUMERO_FATURA   VARCHAR(30)     NOT NULL,
    DATA_EMISSAO    DATE            NOT NULL,
    DATA_VENCIMENTO DATE            NOT NULL,
    DATA_PAGAMENTO  DATE,
    STATUS_FATURA   VARCHAR(15)     DEFAULT 'EM_ABERTO' NOT NULL,
    CONSTRAINT UQ_FATURA_NUMERO UNIQUE (NUMERO_FATURA),
    CONSTRAINT CK_FATURA_STATUS CHECK (STATUS_FATURA IN ('PAGA','EM_ABERTO','ATRASADA','CANCELADA')),
    CONSTRAINT FK_FATURA_TRANSACAO FOREIGN KEY (ID_TRANSACAO) REFERENCES TRANSACOES (ID_TRANSACAO)
);

--------------------------------------------------------------------------------
-- 6. CENTROS_CUSTO
--------------------------------------------------------------------------------
CREATE TABLE CENTROS_CUSTO (
    ID_CENTRO_CUSTO     INTEGER         GENERATED ALWAYS AS IDENTITY (START WITH 1) PRIMARY KEY,
    NOME_CENTRO_CUSTO   VARCHAR(60)     NOT NULL,
    RESPONSAVEL         VARCHAR(100),
    ATIVO               CHAR(1)         DEFAULT 'S' NOT NULL,
    CONSTRAINT CK_CENTRO_CUSTO_ATIVO CHECK (ATIVO IN ('S','N'))
);

--------------------------------------------------------------------------------
-- 7. ORCAMENTOS (valor previsto por categoria/mês, opcionalmente por centro de custo)
--------------------------------------------------------------------------------
CREATE TABLE ORCAMENTOS (
    ID_ORCAMENTO    INTEGER         GENERATED ALWAYS AS IDENTITY (START WITH 1) PRIMARY KEY,
    ID_CATEGORIA    INTEGER         NOT NULL,
    ID_CENTRO_CUSTO INTEGER,
    ANO             NUMERIC(4)      NOT NULL,
    MES             NUMERIC(2)      NOT NULL,
    VALOR_PREVISTO  NUMERIC(15,2)   NOT NULL,
    CONSTRAINT CK_ORCAMENTO_MES CHECK (MES BETWEEN 1 AND 12),
    CONSTRAINT CK_ORCAMENTO_VALOR CHECK (VALOR_PREVISTO >= 0),
    CONSTRAINT UQ_ORCAMENTO UNIQUE (ID_CATEGORIA, ID_CENTRO_CUSTO, ANO, MES),
    CONSTRAINT FK_ORCAMENTO_CATEGORIA FOREIGN KEY (ID_CATEGORIA) REFERENCES CATEGORIAS_FINANCEIRAS (ID_CATEGORIA),
    CONSTRAINT FK_ORCAMENTO_CENTRO_CUSTO FOREIGN KEY (ID_CENTRO_CUSTO) REFERENCES CENTROS_CUSTO (ID_CENTRO_CUSTO)
);

--------------------------------------------------------------------------------
-- 8. TRANSACOES -> relação opcional com CENTROS_CUSTO
--------------------------------------------------------------------------------
ALTER TABLE TRANSACOES ADD COLUMN ID_CENTRO_CUSTO INTEGER;
ALTER TABLE TRANSACOES ADD CONSTRAINT FK_TRANSACAO_CENTRO_CUSTO
    FOREIGN KEY (ID_CENTRO_CUSTO) REFERENCES CENTROS_CUSTO (ID_CENTRO_CUSTO);
