import { provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { Sidebar } from './sidebar';
import { Sessao } from '../../servicos/sessao/sessao';

describe('Sidebar', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Sidebar],
      providers: [provideRouter([])],
    }).compileComponents();
  });

  it('should render the brand logo', async () => {
    const fixture = TestBed.createComponent(Sidebar);
    await fixture.whenStable();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector<HTMLImageElement>('.brand-logo')?.alt).toBe('Grupo Conceito');
  });

  it('mostra o rótulo completo no title do item de menu mesmo com a sidebar expandida, pro texto truncado por CSS não ficar sem tooltip', async () => {
    // Regressão: o title desses itens era condicionado a `colapsado()` —
    // só aparecia com a sidebar recolhida. Mas `.nav-label` trunca o texto
    // por CSS (overflow hidden + nowrap) mesmo expandida, pra rótulos
    // longos como "Específico Grupo Conceito" — sem tooltip nesse caso, o
    // usuário não tinha como ver o nome completo (achado do usuário,
    // 2026-10-01). Corrigido tirando a condição: o title aparece sempre.
    const sessao = TestBed.inject(Sessao);
    sessao.entrar({
      token: 'token-teste',
      usuario: 'usuario.teste',
      nome: 'Usuário Teste',
      foto: null,
      papeis: [],
      administrador: false,
      modulos: ['financeiro'],
    });

    const fixture = TestBed.createComponent(Sidebar);
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const botaoFinanceiro = Array.from(compiled.querySelectorAll('.nav-parent')).find((botao) =>
      botao.textContent?.includes('Financeiro'),
    ) as HTMLButtonElement;
    botaoFinanceiro.click();
    fixture.detectChanges();

    const linkEspecifico = Array.from(compiled.querySelectorAll('.nav-sublink')).find((link) =>
      link.textContent?.includes('Específico Grupo Conceito'),
    );
    expect(linkEspecifico?.getAttribute('title')).toBe('Específico Grupo Conceito');
  });
});
