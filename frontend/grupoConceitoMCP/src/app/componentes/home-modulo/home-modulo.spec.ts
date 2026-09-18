import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Sessao } from '../../servicos/sessao';
import { AtalhoModulo, HomeModulo } from './home-modulo';

describe('HomeModulo', () => {
  let sessao: Sessao;

  beforeEach(async () => {
    localStorage.clear();
    await TestBed.configureTestingModule({
      imports: [HomeModulo],
      providers: [provideRouter([])],
    }).compileComponents();
    sessao = TestBed.inject(Sessao);
  });

  function criarComponente(atalhos: AtalhoModulo[]) {
    const fixture = TestBed.createComponent(HomeModulo);
    fixture.componentRef.setInput('eyebrow', 'Módulo / Visão Geral');
    fixture.componentRef.setInput('titulo', 'Bem-vindo');
    fixture.componentRef.setInput('subtitulo', 'Texto de apoio');
    fixture.componentRef.setInput('atalhos', atalhos);
    fixture.detectChanges();
    return fixture;
  }

  it('renderiza eyebrow, título e subtítulo informados', () => {
    const fixture = criarComponente([]);

    expect(fixture.nativeElement.textContent).toContain('Módulo / Visão Geral');
    expect(fixture.nativeElement.textContent).toContain('Bem-vindo');
    expect(fixture.nativeElement.textContent).toContain('Texto de apoio');
  });

  it('mostra atalho sem somenteAdmin pra usuário sem papel administrador', () => {
    sessao.entrar({
      token: 'token-fake',
      usuario: 'financeiro.teste',
      nome: 'Financeiro Teste',
      foto: null,
      papeis: ['financeiro'],
      administrador: false,
      modulos: ['financeiro'],
    });
    const fixture = criarComponente([
      { titulo: 'Atalho comum', texto: 'texto', rota: '/x', iconeSvg: '' },
    ]);

    expect(fixture.nativeElement.textContent).toContain('Atalho comum');
  });

  it('esconde atalho somenteAdmin pra usuário sem papel administrador', () => {
    sessao.entrar({
      token: 'token-fake',
      usuario: 'financeiro.teste',
      nome: 'Financeiro Teste',
      foto: null,
      papeis: ['financeiro'],
      administrador: false,
      modulos: ['financeiro'],
    });
    const fixture = criarComponente([
      { titulo: 'Atalho admin', texto: 'texto', rota: '/x', somenteAdmin: true, iconeSvg: '' },
    ]);

    expect(fixture.nativeElement.textContent).not.toContain('Atalho admin');
  });

  it('mostra atalho somenteAdmin pra usuário com papel administrador', () => {
    sessao.entrar({
      token: 'token-fake',
      usuario: 'financeiro.admin.teste',
      nome: 'Financeiro Admin Teste',
      foto: null,
      papeis: ['financeiro_admin'],
      administrador: true,
      modulos: ['financeiro'],
    });
    const fixture = criarComponente([
      { titulo: 'Atalho admin', texto: 'texto', rota: '/x', somenteAdmin: true, iconeSvg: '' },
    ]);

    expect(fixture.nativeElement.textContent).toContain('Atalho admin');
  });
});
