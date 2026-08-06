/// <reference types="cypress" />

function selecionarPrimeiraFilial(): void {
  cy.contains('.filtros-topo app-select-busca', 'Filial(is) *').within(() => {
    cy.get('button.gatilho').click();
    cy.get('li button.opcao').first().click();
    cy.get('button.gatilho').click();
  });
}

describe('Financeiro / Fluxo de Caixa', () => {
  beforeEach(() => {
    cy.viewport(1280, 800);
    cy.login(Cypress.env('usuario'), Cypress.env('senha'));
    cy.visit('/financeiro/fluxo-caixa');
    cy.contains('h1', 'Fluxo de Caixa', { timeout: 10000 }).should('be.visible');
  });

  it('gera a previsão mostrando o passo a passo em tempo real, os KPIs, o gráfico e os donuts', () => {
    selecionarPrimeiraFilial();
    cy.contains('button', 'Gerar previsão').click();

    cy.get('.etapas-previsao').should('be.visible');
    cy.get('p.erro-previsao').should('not.exist');

    // A geração de verdade chama o Ollama no fim do streaming (mais lenta
    // aqui, já que soma prazo médio + regressão do A Pagar) — timeout
    // generoso pra não travar num valor curto.
    cy.get('.linha-kpis app-cartao-kpi', { timeout: 90000 }).should('have.length', 5);
    cy.get('.etapas-previsao').should('not.exist');

    // As 4 séries (confirmado + estimado tracejado de cada lado) precisam
    // aparecer todas na legenda — é o que garante que a linha sobreposta do
    // `grafico-serie` (barra + linha tracejada junto) está mesmo renderizando.
    cy.get('.cartao-grafico-principal svg.grafico-svg').should('be.visible');
    cy.get('.cartao-grafico-principal .grafico-legenda .legenda-item').should('have.length', 4);
    cy.contains('.cartao-grafico-principal .legenda-item', 'A Receber (estimado)').should('be.visible');
    cy.contains('.cartao-grafico-principal .legenda-item', 'A Pagar (estimado)').should('be.visible');

    cy.get('.analise-ia').should('be.visible').and('not.be.empty');
    cy.get('.prazo-medio').should('be.visible').and('contain.text', 'Prazo médio');

    cy.get('.grade-donuts app-grafico-rosca').should('have.length', 2);
    cy.get('.grade-donuts .rosca-svg').should('have.length', 2);
  });
});

export {};
