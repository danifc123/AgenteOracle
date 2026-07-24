/// <reference types="cypress" />

declare global {
  namespace Cypress {
    interface Chainable {
      /** Login de verdade pela UI, com `cy.session()` cacheando a sessão
       * entre specs — evita relogar em todo teste. */
      login(usuario: string, senha: string): Chainable<void>;
    }
  }
}

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

export {};
