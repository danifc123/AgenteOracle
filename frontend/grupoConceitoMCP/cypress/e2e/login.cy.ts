/// <reference types="cypress" />

describe('Login', () => {
  beforeEach(() => {
    cy.clearAllLocalStorage();
  });

  it('redireciona pra /login quando não tem sessão', () => {
    cy.visit('/');
    cy.location('pathname').should('eq', '/login');
  });

  it('mostra erro com credenciais inválidas', () => {
    cy.visit('/login');
    cy.get('input[autocomplete="username"]').type('usuario-que-nao-existe');
    cy.get('input[autocomplete="current-password"]').type('senha-errada');
    cy.get('button[type="submit"]').click();

    cy.get('.erro').should('contain.text', 'Usuário ou senha inválidos.');
    cy.location('pathname').should('eq', '/login');
  });

  it('loga com credenciais válidas e cai na Home', () => {
    const usuario = Cypress.env('usuario');
    const senha = Cypress.env('senha');

    cy.visit('/login');
    cy.get('input[autocomplete="username"]').type(usuario);
    cy.get('input[autocomplete="current-password"]').type(senha, { log: false });
    cy.get('button[type="submit"]').click();

    cy.location('pathname', { timeout: 10000 }).should('eq', '/');
  });

  it('bloqueia após muitas tentativas erradas e mostra contagem regressiva', () => {
    // Usuário aleatório (não a conta de teste real): o bloqueio em
    // rate_limit.py é pela string digitada, não por conta existente — assim
    // esse teste não trava a conta usada no teste de login válido.
    const usuarioAleatorio = `bloqueio-teste-${Date.now()}`;

    cy.visit('/login');
    for (let tentativa = 0; tentativa < 5; tentativa++) {
      cy.get('input[autocomplete="username"]').clear().type(usuarioAleatorio);
      cy.get('input[autocomplete="current-password"]').clear().type('senha-errada');
      cy.get('button[type="submit"]').click();
      cy.get('.erro').should('be.visible');
    }

    cy.get('input[autocomplete="username"]').clear().type(usuarioAleatorio);
    cy.get('input[autocomplete="current-password"]').clear().type('senha-errada');
    cy.get('button[type="submit"]').click();

    cy.get('.erro', { timeout: 10000 }).should('contain.text', 'Tente de novo em');
    cy.get('button[type="submit"]').should('be.disabled');
  });
});
