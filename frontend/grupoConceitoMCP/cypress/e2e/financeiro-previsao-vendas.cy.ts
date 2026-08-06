/// <reference types="cypress" />

function selecionarPrimeiraFilial(): void {
  cy.contains('.filtros-topo app-select-busca', 'Filial(is) *').within(() => {
    cy.get('button.gatilho').click();
    cy.get('li button.opcao').first().click();
    cy.get('button.gatilho').click();
  });
}

describe('Financeiro / Projeção de Vendas', () => {
  beforeEach(() => {
    cy.viewport(1280, 800);
    cy.login(Cypress.env('usuario'), Cypress.env('senha'));
    cy.visit('/financeiro/vendas');
    cy.contains('h1', 'Projeção de Vendas', { timeout: 10000 }).should('be.visible');
  });

  it('gera a previsão mostrando o passo a passo em tempo real, os KPIs e o gráfico', () => {
    selecionarPrimeiraFilial();
    cy.contains('button', 'Gerar previsão').click();

    cy.get('.etapas-previsao').should('be.visible');
    cy.get('p.erro-previsao').should('not.exist');

    // A geração de verdade chama o Ollama no fim do streaming — timeout
    // generoso pra não travar num valor curto (mesmo espírito do timeout de
    // 15000ms já usado no teste de "Gerar Relatório").
    cy.get('.linha-kpis app-cartao-kpi', { timeout: 90000 }).should('have.length', 5);
    cy.get('.etapas-previsao').should('not.exist');
    cy.get('.cartao-grafico-principal svg.grafico-svg').should('be.visible');
    cy.get('.analise-ia').should('be.visible').and('not.be.empty');
  });
});

export {};
