import { ViewFinanceira } from '../../../../dadosRelatorios/views-financeiras/views-financeiras';

type ColunasSelecionadas = Record<string, string[]>;
type ValoresFiltros = Record<string, string>;
type FiltrosPorColuna = Record<string, Record<string, string | string[]>>;

function entradaFaixa(
  valores: ValoresFiltros,
  chave: string,
  chaveMin: string,
  chaveMax: string,
): Record<string, string> | null {
  const min = valores[`${chave}_ini`];
  const max = valores[`${chave}_fim`];
  if (!min && !max) {
    return null;
  }
  return { ...(min ? { [chaveMin]: min } : {}), ...(max ? { [chaveMax]: max } : {}) };
}

/** `valores` (lista de valores exatos do select múltiplo, guardados em
 * `valoresFiltros[chave]` como string separada por vírgula) — usado tanto
 * pelo tipo "texto" quanto pelo modo "lista" de "texto-numerico". */
function entradaValores(valores: ValoresFiltros, chave: string): Record<string, string[]> | null {
  if (!valores[chave]) {
    return null;
  }
  const selecionados = valores[chave].split(',').filter(Boolean);
  return selecionados.length ? { valores: selecionados } : null;
}

/** Monta `{"view.coluna": {...}}` a partir de `valoresFiltros`, no formato
 * que cada tipo de coluna espera (texto: `valores`; numero: `min`/`max`;
 * periodo-data: `ini`/`fim`; texto-numerico: os dois ao mesmo tempo —
 * `valores` E/OU `min`/`max`, o que estiver preenchido, já que a tela
 * deixa alternar entre os dois modos pra essa coluna) — só entram colunas
 * com algum valor preenchido. */
export function filtrosPorColuna(
  views: ViewFinanceira[],
  colunasSelecionadas: ColunasSelecionadas,
  valoresFiltros: ValoresFiltros,
): FiltrosPorColuna {
  const filtros: FiltrosPorColuna = {};

  for (const [nomeView, nomesColunas] of Object.entries(colunasSelecionadas)) {
    const view = views.find((item) => item.nome === nomeView);

    for (const nomeColuna of nomesColunas) {
      const chave = `${nomeView}.${nomeColuna}`;
      const tipo = view?.colunas.find((coluna) => coluna.nome === nomeColuna)?.tipo ?? 'texto';

      if (tipo === 'periodo-data') {
        const entrada = entradaFaixa(valoresFiltros, chave, 'ini', 'fim');
        if (entrada) {
          filtros[chave] = entrada;
        }
      } else if (tipo === 'numero') {
        const entrada = entradaFaixa(valoresFiltros, chave, 'min', 'max');
        if (entrada) {
          filtros[chave] = entrada;
        }
      } else if (tipo === 'texto-numerico') {
        const entrada: Record<string, string | string[]> = {
          ...(entradaFaixa(valoresFiltros, chave, 'min', 'max') ?? {}),
          ...(entradaValores(valoresFiltros, chave) ?? {}),
        };
        if (Object.keys(entrada).length) {
          filtros[chave] = entrada;
        }
      } else {
        const entrada = entradaValores(valoresFiltros, chave);
        if (entrada) {
          filtros[chave] = entrada;
        }
      }
    }
  }

  return filtros;
}
