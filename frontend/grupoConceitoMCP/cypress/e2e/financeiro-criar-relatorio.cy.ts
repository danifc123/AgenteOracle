/// <reference types="cypress" />

const API_BASE_URL = 'http://127.0.0.1:8000';

function abrirPrimeiraTabelaEMarcarColuna(): void {
  cy.get('.painel-lista-corpo button.tabela-cabecalho').first().click();
  cy.get('.tabela-colunas label.coluna-item input[type=checkbox]').first().check();
}

function selecionarPrimeiraFilial(): void {
  cy.contains('.campos-grid app-select-busca', 'Filial(is) *').within(() => {
    cy.get('button.gatilho').click();
    cy.get('li button.opcao').first().click();
    cy.get('button.gatilho').click();
  });
}

describe('Financeiro / Criar Relatório', () => {
  let layoutCriadoId: number | undefined;

  beforeEach(() => {
    cy.viewport(1280, 800);
    cy.login(Cypress.env('usuario'), Cypress.env('senha'));
    cy.visit('/financeiro/criar-relatorio');
    cy.get('.painel-lista-corpo button.tabela-cabecalho', { timeout: 10000 }).should(
      'have.length.greaterThan',
      0
    );
  });

  it('lista tabelas disponíveis e a busca filtra a lista', () => {
    cy.get('.painel-lista-corpo button.tabela-cabecalho')
      .its('length')
      .then((total) => {
        cy.get('.busca input[type=text]').type('tabela-que-nao-existe-cypress');
        cy.get('.painel-lista-corpo p.lista-vazia').should('be.visible');

        cy.get('.busca button.limpar').click();
        cy.get('.painel-lista-corpo button.tabela-cabecalho').should('have.length', total);
      });
  });

  it('gera um relatório de verdade com uma tabela, coluna e filial', () => {
    abrirPrimeiraTabelaEMarcarColuna();
    selecionarPrimeiraFilial();

    cy.contains('.detalhe-acoes button', 'Gerar Relatório').click();

    cy.get('div.painel[role=dialog]', { timeout: 10000 }).should('be.visible');
    cy.get('div.painel[role=dialog] p.erro-exportacao').should('not.exist');
    cy.get('div.painel[role=dialog]', { timeout: 15000 }).should(
      'not.contain.text',
      'Carregando relatório...'
    );

    cy.get('button.fechar[aria-label="Fechar"]').click();
    cy.get('div.painel[role=dialog]').should('not.exist');
  });

  it('salva um layout novo (apagado via API no final, não deixa lixo na conta real)', () => {
    const nomeLayout = `cypress-layout-${Date.now()}`;

    abrirPrimeiraTabelaEMarcarColuna();
    selecionarPrimeiraFilial();

    cy.intercept('POST', '**/api/financeiro/relatorio/layouts').as('salvarLayout');

    cy.contains('.detalhe-acoes button', 'Salvar layout').click();
    cy.get('.painel[role=dialog] label.campo input[type=text]').type(nomeLayout);
    cy.get('.painel[role=dialog]').contains('button', 'Salvar').click();

    cy.wait('@salvarLayout').then((interceptacao) => {
      expect(interceptacao.response?.statusCode).to.eq(201);
      layoutCriadoId = interceptacao.response?.body?.id;
      expect(layoutCriadoId).to.be.a('number');
    });

    cy.get('.painel[role=dialog]').should('not.exist');
  });

  after(() => {
    if (!layoutCriadoId) {
      return;
    }
    cy.tokenApi().then((token) => {
      cy.request({
        method: 'DELETE',
        url: `${API_BASE_URL}/api/financeiro/relatorio/layouts/${layoutCriadoId}`,
        headers: { Authorization: `Bearer ${token}` },
        failOnStatusCode: false
      });
    });
  });
});

export {};
