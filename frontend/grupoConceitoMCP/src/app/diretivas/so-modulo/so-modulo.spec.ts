import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Sessao } from '../../servicos/sessao/sessao';
import { SoModulo } from './so-modulo';

@Component({
  imports: [SoModulo],
  template: `<div *appSoModulo="'financeiro'">conteudo-financeiro</div>`,
})
class HostTeste {}

describe('SoModulo', () => {
  let sessao: Sessao;

  beforeEach(async () => {
    localStorage.clear();
    await TestBed.configureTestingModule({
      imports: [HostTeste],
      providers: [provideRouter([])],
    }).compileComponents();
    sessao = TestBed.inject(Sessao);
  });

  it('esconde o conteúdo pra usuário sem acesso ao módulo pedido', async () => {
    const fixture = TestBed.createComponent(HostTeste);
    sessao.entrar({
      token: 'token-fake',
      usuario: 'rh.teste',
      nome: 'RH Teste',
      foto: null,
      papeis: ['rh'],
      administrador: false,
      modulos: ['rh'],
    });
    fixture.detectChanges();
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent).not.toContain('conteudo-financeiro');
  });

  it('mostra o conteúdo pra usuário com acesso ao módulo pedido', async () => {
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

    expect(fixture.nativeElement.textContent).toContain('conteudo-financeiro');
  });
});
