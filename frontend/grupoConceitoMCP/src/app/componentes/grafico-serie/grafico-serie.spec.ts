import { TestBed } from '@angular/core/testing';
import { GraficoSerie, SerieGrafico } from './grafico-serie';

const SERIE: SerieGrafico[] = [
  {
    nome: 'Tokens',
    cor: '#1b4332',
    pontos: [
      { rotulo: '23/09', valor: 1200 },
      { rotulo: '24/09', valor: 3400 },
    ],
  },
];

function criar(unidade?: 'moeda' | 'numero') {
  const fixture = TestBed.createComponent(GraficoSerie);
  fixture.componentRef.setInput('series', SERIE);
  if (unidade) {
    fixture.componentRef.setInput('unidade', unidade);
  }
  fixture.detectChanges();

  const el: HTMLElement = fixture.nativeElement;
  return {
    rotulosY: () => Array.from(el.querySelectorAll('.grafico-rotulo-y')).map((n) => n.textContent?.trim()),
  };
}

describe('GraficoSerie', () => {
  it('sem "unidade" informada, formata os rótulos do eixo Y como moeda (comportamento de sempre)', () => {
    const { rotulosY } = criar();

    expect(rotulosY().some((texto) => texto?.includes('R$'))).toBe(true);
  });

  it('unidade="moeda" explícita também formata como moeda', () => {
    const { rotulosY } = criar('moeda');

    expect(rotulosY().some((texto) => texto?.includes('R$'))).toBe(true);
  });

  it('unidade="numero" não abrevia nem prefixa "R$"', () => {
    const { rotulosY } = criar('numero');

    expect(rotulosY().some((texto) => texto?.includes('R$'))).toBe(false);
    // Topo do eixo = maior valor (3400) * 1.15 de margem = 3910, formatado
    // como número puro com separador de milhar (não abreviado tipo "3,9 Mil").
    expect(rotulosY()).toContain('3.910');
  });
});
