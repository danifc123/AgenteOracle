export type DirecaoOrdenacao = 'asc' | 'desc' | null;

/** Ciclo de 3 estados ao clicar num cabeçalho de coluna: neutro (ordem
 * original) -> A-Z -> Z-A -> neutro de novo. */
export function proximaDirecao(atual: DirecaoOrdenacao): DirecaoOrdenacao {
  if (atual === null) return 'asc';
  if (atual === 'asc') return 'desc';
  return null;
}

const _PADRAO_DATA_BR = /^(\d{2})\/(\d{2})\/(\d{4})$/;

/** Várias colunas de data (views VWIA_*, ex: vwia_notas_compra.data_emissao —
 * ver `db/views/financeiro_science.sql`) chegam do backend já formatadas
 * como texto "DD/MM/YYYY", não uma data/ISO string. Comparar esse texto
 * com `localeCompare({numeric: true})` compara pedaço por pedaço na ordem
 * em que aparece no texto (dia, depois mês, só por último ano) — group a
 * tabela por DIA antes de por ANO, misturando anos diferentes fora de
 * ordem. Reconhece o formato e devolve um número comparável
 * cronologicamente (AAAAMMDD); `null` se `valor` não bater com o padrão. */
function dataBrComparavel(valor: unknown): number | null {
  if (typeof valor !== 'string') {
    return null;
  }
  const encontrado = _PADRAO_DATA_BR.exec(valor);
  if (!encontrado) {
    return null;
  }
  const [, dia, mes, ano] = encontrado;
  return Number(`${ano}${mes}${dia}`);
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

  const dataA = dataBrComparavel(valorA);
  const dataB = dataBrComparavel(valorB);
  if (dataA !== null && dataB !== null) {
    return dataA - dataB;
  }

  return String(valorA).localeCompare(String(valorB), 'pt-BR', {
    numeric: true,
    sensitivity: 'base',
  });
}
