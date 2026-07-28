/// <reference types="cypress" />

const NOME_ROTINA = 'Fluxo de Caixa Realizado';

function selecionarPrimeiraFilial(): void {
  cy.contains('.campos-grid app-select-busca', 'Filial(is) *').within(() => {
    cy.get('button.gatilho').click();
    cy.get('li button.opcao').first().click();
    cy.get('button.gatilho').click();
  });
}

describe('Financeiro / Específico Grupo Conceito (rotinas)', () => {
  beforeEach(() => {
    cy.viewport(1280, 800);
    cy.login(Cypress.env('usuario'), Cypress.env('senha'));
    cy.visit('/financeiro/especifico-grupo-conceito');
    cy.contains('button.rotina-linha', NOME_ROTINA, { timeout: 10000 }).should('be.visible');
  });

  it('gera o relatório de uma rotina simples e, se houver dados, permite ordenar por coluna', () => {
    cy.contains('button.rotina-linha', NOME_ROTINA).click();
    selecionarPrimeiraFilial();
    cy.get('input.campo-texto[aria-label="Ano"]').type('2024');

    cy.contains('.detalhe-acoes button', 'Ver Relatório').click();

    cy.get('div.painel[role=dialog]', { timeout: 10000 }).should('be.visible');
    cy.get('div.painel[role=dialog] p.erro-exportacao').should('not.exist');
    cy.get('div.painel[role=dialog]', { timeout: 15000 }).should(
      'not.contain.text',
      'Carregando relatório...'
    );

    cy.get('div.painel[role=dialog]').then(($dialog) => {
      const primeiraColuna = $dialog.find('table.planilha th.ordenavel').first();
      if (primeiraColuna.length) {
        cy.wrap(primeiraColuna).click();
        cy.wrap(primeiraColuna).find('svg.icone-ordenacao').should('have.class', 'ativo');
      }
    });

    cy.get('button.fechar[aria-label="Fechar"]').click();
  });

  it('fixa e desfixa uma rotina (estado só local, não mexe em conta real)', () => {
    cy.contains('button.rotina-linha', NOME_ROTINA).click();

    cy.get('button.botao-fixar').should('not.have.class', 'botao-fixar--ativo');
    cy.get('button.botao-fixar').click();
    cy.get('button.botao-fixar').should('have.class', 'botao-fixar--ativo');
    cy.get('button.botao-fixar').click();
    cy.get('button.botao-fixar').should('not.have.class', 'botao-fixar--ativo');
  });
});

export {};
