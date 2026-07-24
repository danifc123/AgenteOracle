/// <reference types="cypress" />

const API_BASE_URL = 'http://127.0.0.1:8000';

function abrirConfiguracoes(): void {
  cy.get('button.config[aria-label="Configurações"]').click();
  cy.get('div.painel[role=dialog]').should('be.visible');
}

describe('Configurações', () => {
  const nomeLayoutSetup = `cypress-config-${Date.now()}`;
  let idLayoutSetup: number | undefined;

  before(() => {
    cy.tokenApi().then((token) => {
      cy.request({
        method: 'POST',
        url: `${API_BASE_URL}/api/financeiro/relatorio/layouts`,
        headers: { Authorization: `Bearer ${token}` },
        body: {
          nome: nomeLayoutSetup,
          colunas_selecionadas: { cypress_setup: ['coluna_teste'] },
          valores_filtros: {},
          filiais_selecionadas: []
        }
      }).then((resposta) => {
        idLayoutSetup = resposta.body.id;
      });
    });
  });

  beforeEach(() => {
    cy.viewport(1280, 800);
    cy.login(Cypress.env('usuario'), Cypress.env('senha'));
    cy.visit('/');
  });

  after(() => {
    if (!idLayoutSetup) {
      return;
    }
    cy.tokenApi().then((token) => {
      cy.request({
        method: 'DELETE',
        url: `${API_BASE_URL}/api/financeiro/relatorio/layouts/${idLayoutSetup}`,
        headers: { Authorization: `Bearer ${token}` },
        failOnStatusCode: false
      });
    });
  });

  it('abre o dialog com as seções esperadas e permite colapsar/expandir', () => {
    abrirConfiguracoes();

    cy.get('div.painel[role=dialog] header h2').should('contain.text', 'Configurações');
    cy.contains('.secao h3', 'Perfil').should('be.visible');
    cy.contains('.secao h3', 'Senha').should('be.visible');
    cy.contains('.secao h3', 'Layouts salvos').scrollIntoView().should('be.visible');
    cy.contains('.secao h3', 'Cores das categorias').scrollIntoView().should('be.visible');

    cy.contains('button.secao-cabecalho', 'Layouts salvos')
      .scrollIntoView()
      .should('have.attr', 'aria-expanded', 'true');
    cy.contains('button.secao-cabecalho', 'Layouts salvos').click();
    cy.contains('button.secao-cabecalho', 'Layouts salvos').should('have.attr', 'aria-expanded', 'false');
    cy.contains('button.secao-cabecalho', 'Layouts salvos').click();

    cy.get('button.fechar[aria-label="Fechar"]').click();
    cy.get('div.painel[role=dialog]').should('not.exist');
  });

  it('edita o nome do perfil e reverte pro original em seguida', () => {
    abrirConfiguracoes();

    cy.get('label.campo input[type=text]')
      .invoke('val')
      .then((nomeOriginal) => {
        const nomeTeste = `Cypress Teste ${Date.now()}`;

        cy.intercept('PATCH', '**/api/auth/perfil').as('salvarPerfil');
        cy.get('label.campo input[type=text]').clear().type(nomeTeste);
        cy.contains('button', 'Salvar perfil').click();
        cy.wait('@salvarPerfil').its('response.statusCode').should('eq', 200);
        cy.get('.secao').first().find('p.erro').should('not.exist');

        cy.intercept('PATCH', '**/api/auth/perfil').as('reverterPerfil');
        cy.get('label.campo input[type=text]').clear().type(String(nomeOriginal));
        cy.contains('button', 'Salvar perfil').click();
        cy.wait('@reverterPerfil').its('response.statusCode').should('eq', 200);
        cy.get('.secao').first().find('p.erro').should('not.exist');
      });

    cy.get('button.fechar[aria-label="Fechar"]').click();
  });

  it('muda a cor de uma categoria e depois redefine pro padrão', () => {
    abrirConfiguracoes();

    cy.get('li.cor-categoria-item')
      .first()
      .scrollIntoView()
      .within(() => {
        cy.intercept('PUT', '**/api/financeiro/categorias/cores/**').as('salvarCor');
        cy.get('input[type=color]').invoke('val', '#123456').trigger('change');
        cy.wait('@salvarCor').its('response.statusCode').should('eq', 200);
        cy.get('button.cor-categoria-redefinir').should('be.visible');

        cy.intercept('DELETE', '**/api/financeiro/categorias/cores/**').as('redefinirCor');
        cy.get('button.cor-categoria-redefinir').click();
        cy.wait('@redefinirCor').its('response.statusCode').should('eq', 200);
        cy.get('button.cor-categoria-redefinir').should('not.exist');
      });

    cy.get('button.fechar[aria-label="Fechar"]').click();
  });

  it('renomeia e apaga um layout salvo (criado via API só pra esse teste)', () => {
    abrirConfiguracoes();

    const nomeRenomeado = `${nomeLayoutSetup}-renomeado`;

    cy.contains('li.layout-item', nomeLayoutSetup)
      .scrollIntoView()
      .within(() => {
        cy.get('button[aria-label="Renomear layout"]').click();
        cy.get('input.input-edicao-layout').should('be.visible').clear().type(nomeRenomeado);

        cy.intercept('PATCH', '**/api/financeiro/relatorio/layouts/**').as('renomearLayout');
        cy.get('button[aria-label="Salvar nome"]').click();
        cy.wait('@renomearLayout').its('response.statusCode').should('eq', 200);
      });

    cy.contains('li.layout-item', nomeRenomeado).scrollIntoView().should('be.visible');

    cy.on('window:confirm', () => true);
    cy.intercept('DELETE', '**/api/financeiro/relatorio/layouts/**').as('apagarLayout');
    cy.contains('li.layout-item', nomeRenomeado).scrollIntoView().contains('button', 'Apagar').click();
    cy.wait('@apagarLayout').its('response.statusCode').should('eq', 200);

    cy.contains('li.layout-item', nomeRenomeado).should('not.exist');
    idLayoutSetup = undefined;

    cy.get('button.fechar[aria-label="Fechar"]').click();
  });
});

export {};
