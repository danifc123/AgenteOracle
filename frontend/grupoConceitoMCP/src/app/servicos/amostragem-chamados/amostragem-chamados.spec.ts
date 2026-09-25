import { analisadosPorDez, percentualValido } from './amostragem-chamados';

describe('percentualValido', () => {
  it.each([
    ['20', 20],
    ['0', 0],
    ['100', 100],
    ['33.333', 33.333],
    ['33,333', 33.333],
    [' 12.5 ', 12.5],
    ['33.3330', 33.333],
  ])('aceita "%s"', (texto, esperado) => {
    expect(percentualValido(texto)).toBe(esperado);
  });

  it.each(['', '   ', 'abc', '-1', '100.001', '101', '33.3333', '1e2', '12,3,4'])(
    'rejeita "%s"',
    (texto) => {
      expect(percentualValido(texto)).toBeNull();
    },
  );
});

describe('analisadosPorDez', () => {
  it.each([
    [20, 2],
    [29, 2], // com float, 29% × 10 daria 2,9 e um arredondamento errado perderia/ganharia um
    [33.333, 3],
    [50, 5],
    [100, 10],
    [0, 0],
    [0.5, 0],
    [99.999, 9],
  ])('%s%% → %s de cada 10 (sempre arredondando pra baixo)', (percentual, esperado) => {
    expect(analisadosPorDez(percentual)).toBe(esperado);
  });
});
