export type DirecaoOrdenacao = 'asc' | 'desc' | null;

/** Ciclo de 3 estados ao clicar num cabeçalho de coluna: neutro (ordem
 * original) -> A-Z -> Z-A -> neutro de novo. */
export function proximaDirecao(atual: DirecaoOrdenacao): DirecaoOrdenacao {
  if (atual === null) return 'asc';
  if (atual === 'asc') return 'desc';
  return null;
}

export function compararValores(valorA: unknown, valorB: unknown): number {
  const vazioA = valorA === null || valorA === undefined || valorA === '';
  const vazioB = valorB === null || valorB === undefined || valorB === '';
  if (vazioA && vazioB) return 0;
  if (vazioA) return 1;
  if (vazioB) return -1;

  if (typeof valorA === 'number' && typeof valorB === 'number') {
    return valorA - valorB;
  }

  return String(valorA).localeCompare(String(valorB), 'pt-BR', { numeric: true, sensitivity: 'base' });
}
