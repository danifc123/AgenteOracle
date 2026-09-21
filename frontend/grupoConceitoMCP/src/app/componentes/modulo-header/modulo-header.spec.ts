import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { SoDev } from '../../diretivas/so-dev/so-dev';
import { Sessao } from '../../servicos/sessao/sessao';
import { ModuloHeader } from './modulo-header';

// Slot `acoes` atrás de `*appSoDev`: dev vê, os demais não.
@Component({
  imports: [ModuloHeader, SoDev],
  template: `
    <app-modulo-header breadcrumb="TI" titulo="Auditoria de Chamados" descricao="Texto de apoio">
      <div acoes *appSoDev class="engrenagem">config</div>
    </app-modulo-header>
  `,
})
class HostTeste {}

describe('ModuloHeader', () => {
  let sessao: Sessao;

  beforeEach(async () => {
    localStorage.clear();
    await TestBed.configureTestingModule({
      imports: [HostTeste],
      providers: [provideRouter([])],
    }).compileComponents();
    sessao = TestBed.inject(Sessao);
  });

  it('mostra título, breadcrumb e descrição', () => {
    const fixture = TestBed.createComponent(HostTeste);
    fixture.detectChanges();

    const texto = fixture.nativeElement.textContent;
    expect(texto).toContain('Auditoria de Chamados');
    expect(texto).toContain('TI');
    expect(texto).toContain('Texto de apoio');
  });

  it('desenvolvedor vê o conteúdo do slot "acoes" dentro do cabeçalho', async () => {
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

    const engrenagem = fixture.nativeElement.querySelector('header .engrenagem');
    expect(engrenagem?.textContent).toBe('config');
  });

  it('usuário sem o papel desenvolvedor não vê nada no slot "acoes"', async () => {
    const fixture = TestBed.createComponent(HostTeste);
    sessao.entrar({
      token: 'token-fake',
      usuario: 'ti.teste',
      nome: 'TI Teste',
      foto: null,
      papeis: ['ti_admin'],
      administrador: true,
      modulos: ['ti'],
    });
    fixture.detectChanges();
    await fixture.whenStable();

    expect(fixture.nativeElement.querySelector('.engrenagem')).toBeNull();
  });
});
