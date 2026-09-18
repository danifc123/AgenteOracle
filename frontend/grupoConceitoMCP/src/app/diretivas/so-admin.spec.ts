import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Sessao } from '../servicos/sessao';
import { SoAdmin } from './so-admin';

@Component({
  imports: [SoAdmin],
  template: `<div *appSoAdmin>conteudo-admin</div>`,
})
class HostTeste {}

describe('SoAdmin', () => {
  let sessao: Sessao;

  beforeEach(async () => {
    localStorage.clear();
    await TestBed.configureTestingModule({
      imports: [HostTeste],
      providers: [provideRouter([])],
    }).compileComponents();
    sessao = TestBed.inject(Sessao);
  });

  it('esconde o conteúdo pra usuário sem papel administrador', async () => {
    const fixture = TestBed.createComponent(HostTeste);
    sessao.entrar({
      token: 'token-fake',
      usuario: 'financeiro.teste',
      nome: 'Financeiro Teste',
      foto: null,
      papeis: ['financeiro'],
      administrador: false,
      modulos: ['financeiro'],
    });
    fixture.detectChanges();
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent).not.toContain('conteudo-admin');
  });

  it('mostra o conteúdo pra usuário com algum papel administrador', async () => {
    const fixture = TestBed.createComponent(HostTeste);
    sessao.entrar({
      token: 'token-fake',
      usuario: 'financeiro.admin.teste',
      nome: 'Financeiro Admin Teste',
      foto: null,
      papeis: ['financeiro_admin'],
      administrador: true,
      modulos: ['financeiro'],
    });
    fixture.detectChanges();
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent).toContain('conteudo-admin');
  });
});
