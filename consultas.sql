--------------------------------------------------------------------------------
-- MODELAGEM DE BANCO DE DADOS - DEPARTAMENTO FINANCEIRO (AMBIENTE DE TESTE)
-- SGBD: Oracle (Oracle SQL Developer)
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
BEGIN
   FOR t IN (SELECT table_name FROM user_tables
             WHERE table_name IN ('ORCAMENTOS','FATURAS','TRANSACOES','CENTROS_CUSTO',
                                   'FORNECEDORES_CLIENTES','CATEGORIAS_FINANCEIRAS',
                                   'CONTAS_BANCARIAS'))
   LOOP
      EXECUTE IMMEDIATE 'DROP TABLE ' || t.table_name || ' CASCADE CONSTRAINTS PURGE';
   END LOOP;
END;
/

--------------------------------------------------------------------------------
-- 1. CONTAS_BANCARIAS
--------------------------------------------------------------------------------
CREATE TABLE CONTAS_BANCARIAS (
    ID_CONTA        NUMBER          GENERATED ALWAYS AS IDENTITY (START WITH 1) PRIMARY KEY,
    NOME_CONTA      VARCHAR2(100)   NOT NULL,
    BANCO           VARCHAR2(50)    NOT NULL,
    AGENCIA         VARCHAR2(10),
    NUMERO_CONTA    VARCHAR2(20),
    TIPO_CONTA      VARCHAR2(20)    NOT NULL,
    SALDO_ATUAL     NUMBER(15,2)    DEFAULT 0 NOT NULL,
    DATA_ABERTURA   DATE            NOT NULL,
    CONSTRAINT CK_CONTAS_TIPO CHECK (TIPO_CONTA IN ('CORRENTE','POUPANCA','INVESTIMENTO'))
);

--------------------------------------------------------------------------------
-- 2. CATEGORIAS_FINANCEIRAS
--------------------------------------------------------------------------------
CREATE TABLE CATEGORIAS_FINANCEIRAS (
    ID_CATEGORIA    NUMBER          GENERATED ALWAYS AS IDENTITY (START WITH 1) PRIMARY KEY,
    NOME_CATEGORIA  VARCHAR2(60)    NOT NULL,
    TIPO_CATEGORIA  VARCHAR2(10)    NOT NULL,
    DESCRICAO       VARCHAR2(200),
    CONSTRAINT CK_CATEGORIA_TIPO CHECK (TIPO_CATEGORIA IN ('RECEITA','DESPESA'))
);

--------------------------------------------------------------------------------
-- 3. FORNECEDORES_CLIENTES
--------------------------------------------------------------------------------
CREATE TABLE FORNECEDORES_CLIENTES (
    ID_ENTIDADE     NUMBER          GENERATED ALWAYS AS IDENTITY (START WITH 1) PRIMARY KEY,
    NOME            VARCHAR2(100)   NOT NULL,
    TIPO_ENTIDADE   VARCHAR2(15)    NOT NULL,
    CNPJ_CPF        VARCHAR2(20),
    EMAIL           VARCHAR2(100),
    TELEFONE        VARCHAR2(20),
    CONSTRAINT CK_ENTIDADE_TIPO CHECK (TIPO_ENTIDADE IN ('FORNECEDOR','CLIENTE'))
);

--------------------------------------------------------------------------------
-- 4. TRANSACOES
--------------------------------------------------------------------------------
CREATE TABLE TRANSACOES (
    ID_TRANSACAO    NUMBER          GENERATED ALWAYS AS IDENTITY (START WITH 1) PRIMARY KEY,
    ID_CONTA        NUMBER          NOT NULL,
    ID_CATEGORIA    NUMBER          NOT NULL,
    ID_ENTIDADE     NUMBER,
    TIPO_TRANSACAO  VARCHAR2(10)    NOT NULL,
    DESCRICAO       VARCHAR2(200)   NOT NULL,
    VALOR           NUMBER(15,2)    NOT NULL,
    DATA_TRANSACAO  DATE            NOT NULL,
    STATUS_TRANSACAO VARCHAR2(15)   DEFAULT 'PENDENTE' NOT NULL,
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
    ID_FATURA       NUMBER          GENERATED ALWAYS AS IDENTITY (START WITH 1) PRIMARY KEY,
    ID_TRANSACAO    NUMBER          NOT NULL,
    NUMERO_FATURA   VARCHAR2(30)    NOT NULL,
    DATA_EMISSAO    DATE            NOT NULL,
    DATA_VENCIMENTO DATE            NOT NULL,
    DATA_PAGAMENTO  DATE,
    STATUS_FATURA   VARCHAR2(15)    DEFAULT 'EM_ABERTO' NOT NULL,
    CONSTRAINT UQ_FATURA_NUMERO UNIQUE (NUMERO_FATURA),
    CONSTRAINT CK_FATURA_STATUS CHECK (STATUS_FATURA IN ('PAGA','EM_ABERTO','ATRASADA','CANCELADA')),
    CONSTRAINT FK_FATURA_TRANSACAO FOREIGN KEY (ID_TRANSACAO) REFERENCES TRANSACOES (ID_TRANSACAO)
);

--------------------------------------------------------------------------------
-- 6. CENTROS_CUSTO
--------------------------------------------------------------------------------
CREATE TABLE CENTROS_CUSTO (
    ID_CENTRO_CUSTO     NUMBER          GENERATED ALWAYS AS IDENTITY (START WITH 1) PRIMARY KEY,
    NOME_CENTRO_CUSTO   VARCHAR2(60)    NOT NULL,
    RESPONSAVEL         VARCHAR2(100),
    ATIVO               CHAR(1)         DEFAULT 'S' NOT NULL,
    CONSTRAINT CK_CENTRO_CUSTO_ATIVO CHECK (ATIVO IN ('S','N'))
);

--------------------------------------------------------------------------------
-- 7. ORCAMENTOS (valor previsto por categoria/mês, opcionalmente por centro de custo)
--------------------------------------------------------------------------------
CREATE TABLE ORCAMENTOS (
    ID_ORCAMENTO    NUMBER          GENERATED ALWAYS AS IDENTITY (START WITH 1) PRIMARY KEY,
    ID_CATEGORIA    NUMBER          NOT NULL,
    ID_CENTRO_CUSTO NUMBER,
    ANO             NUMBER(4)       NOT NULL,
    MES             NUMBER(2)       NOT NULL,
    VALOR_PREVISTO  NUMBER(15,2)    NOT NULL,
    CONSTRAINT CK_ORCAMENTO_MES CHECK (MES BETWEEN 1 AND 12),
    CONSTRAINT CK_ORCAMENTO_VALOR CHECK (VALOR_PREVISTO >= 0),
    CONSTRAINT UQ_ORCAMENTO UNIQUE (ID_CATEGORIA, ID_CENTRO_CUSTO, ANO, MES),
    CONSTRAINT FK_ORCAMENTO_CATEGORIA FOREIGN KEY (ID_CATEGORIA) REFERENCES CATEGORIAS_FINANCEIRAS (ID_CATEGORIA),
    CONSTRAINT FK_ORCAMENTO_CENTRO_CUSTO FOREIGN KEY (ID_CENTRO_CUSTO) REFERENCES CENTROS_CUSTO (ID_CENTRO_CUSTO)
);

--------------------------------------------------------------------------------
-- 8. TRANSACOES -> relação opcional com CENTROS_CUSTO
--------------------------------------------------------------------------------
ALTER TABLE TRANSACOES ADD ID_CENTRO_CUSTO NUMBER;
ALTER TABLE TRANSACOES ADD CONSTRAINT FK_TRANSACAO_CENTRO_CUSTO
    FOREIGN KEY (ID_CENTRO_CUSTO) REFERENCES CENTROS_CUSTO (ID_CENTRO_CUSTO);
