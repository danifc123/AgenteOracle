import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Sessao } from '../servicos/sessao';
import { SoDev } from './so-dev';

@Component({
  imports: [SoDev],
  template: `<div *appSoDev>conteudo-dev</div>`,
})
class HostTeste {}

describe('SoDev', () => {
  let sessao: Sessao;

  beforeEach(async () => {
    localStorage.clear();
    await TestBed.configureTestingModule({
      imports: [HostTeste],
      providers: [provideRouter([])],
    }).compileComponents();
    sessao = TestBed.inject(Sessao);
  });

  it('esconde o conteúdo quando ninguém está logado', async () => {
    const fixture = TestBed.createComponent(HostTeste);
    fixture.detectChanges();
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent).not.toContain('conteudo-dev');
  });

  it('esconde o conteúdo pra usuário logado sem o papel desenvolvedor', async () => {
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

    expect(fixture.nativeElement.textContent).not.toContain('conteudo-dev');
  });

  it('mostra o conteúdo pra usuário com o papel desenvolvedor', async () => {
    const fixture = TestBed.createComponent(HostTeste);
    sessao.entrar({
      token: 'token-fake',
      usuario: 'dev.teste',
      nome: 'Dev Teste',
      foto: null,
      papeis: ['desenvolvedor'],
      administrador: true,
      modulos: ['ti'],
    });
    fixture.detectChanges();
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent).toContain('conteudo-dev');
  });
});
