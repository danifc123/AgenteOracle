/// <reference types="cypress" />

declare global {
  namespace Cypress {
    interface Chainable {
      /** Login de verdade pela UI, com `cy.session()` cacheando a sessão
       * entre specs — evita relogar em todo teste. */
      login(usuario: string, senha: string): Chainable<void>;
      /** Loga direto na API (sem passar pela UI) e devolve o token JWT —
       * usado só por specs que precisam de `cy.request()` autenticado pra
       * criar/apagar dados de setup e cleanup (ex: layouts de teste). */
      tokenApi(): Chainable<string>;
    }
  }
}

const API_BASE_URL = 'http://127.0.0.1:8000';

Cypress.Commands.add('login', (usuario: string, senha: string) => {
  cy.session(
    [usuario, senha],
    () => {
      cy.visit('/login');
      cy.get('input[autocomplete="username"]').type(usuario);
      cy.get('input[autocomplete="current-password"]').type(senha, { log: false });
      cy.get('button[type="submit"]').click();
      cy.location('pathname', { timeout: 10000 }).should('eq', '/');
    },
    {
      validate: () => {
        cy.window().then((janela) => {
          expect(janela.localStorage.getItem('sessao:usuario')).to.exist;
        });
      }
    }
  );
});

Cypress.Commands.add('tokenApi', () => {
  return cy
    .request('POST', `${API_BASE_URL}/api/auth/login`, {
      usuario: Cypress.env('usuario'),
      senha: Cypress.env('senha')
    })
    .its('body.token');
});

export {};
