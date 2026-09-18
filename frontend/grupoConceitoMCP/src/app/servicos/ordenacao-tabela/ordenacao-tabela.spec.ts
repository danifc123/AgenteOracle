import { compararValores, proximaDirecao } from './ordenacao-tabela';

describe('proximaDirecao', () => {
  it('cicla neutro -> asc -> desc -> neutro', () => {
    expect(proximaDirecao(null)).toBe('asc');
    expect(proximaDirecao('asc')).toBe('desc');
    expect(proximaDirecao('desc')).toBe(null);
  });
});

describe('compararValores', () => {
  it('compara números diretamente', () => {
    expect(compararValores(10, 2)).toBeGreaterThan(0);
    expect(compararValores(2, 10)).toBeLessThan(0);
  });

  it('vazio (null/undefined/string vazia) sempre vai pro fim', () => {
    expect(compararValores(null, 'x')).toBeGreaterThan(0);
    expect(compararValores('x', undefined)).toBeLessThan(0);
    expect(compararValores('', 'x')).toBeGreaterThan(0);
  });

  it('texto comum usa comparação numérica de locale (ex: "item2" antes de "item10")', () => {
    expect(compararValores('item2', 'item10')).toBeLessThan(0);
  });

  it('data no formato DD/MM/YYYY (views VWIA_*) ordena cronologicamente, não por dia/mês primeiro', () => {
    // Caso real reportado: 31/12/2025 e 31/10/2025 têm o mesmo dia (31) e
    // meses diferentes (12 vs 10) — comparação ingênua de texto colocaria
    // "31/10/2024" antes de "31/12/2025" mesmo sendo mais recente por ano/mês.
    expect(compararValores('31/12/2025', '31/10/2024')).toBeGreaterThan(0);
    expect(compararValores('31/10/2025', '31/12/2024')).toBeGreaterThan(0);
  });

  it('lista de datas DD/MM/YYYY ordenada cronologicamente fica na ordem certa', () => {
    const datas = ['31/10/2023', '31/12/2025', '31/12/2024', '31/10/2025', '31/10/2024'];
    const ordenadas = [...datas].sort(compararValores);
    expect(ordenadas).toEqual(['31/10/2023', '31/10/2024', '31/12/2024', '31/10/2025', '31/12/2025']);
  });

  it('texto que não bate no formato DD/MM/YYYY cai na comparação genérica de locale', () => {
    expect(compararValores('31/12/2025', 'abc')).toBe(
      '31/12/2025'.localeCompare('abc', 'pt-BR', { numeric: true, sensitivity: 'base' }),
    );
  });
});
