import { ViewFinanceira } from '../../../../dadosRelatorios/views-financeiras';

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

/** Monta `{"view.coluna": {...}}` a partir de `valoresFiltros`, no formato
 * que cada tipo de coluna espera (texto: `valores`, lista de valores exatos
 * escolhidos no select multiplo — guardados como string separada por
 * vírgula; numero: `min`/`max`; periodo-data: `ini`/`fim`) — só entram
 * colunas com algum valor preenchido. */
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
      } else if (valoresFiltros[chave]) {
        const selecionados = valoresFiltros[chave].split(',').filter(Boolean);
        if (selecionados.length) {
          filtros[chave] = { valores: selecionados };
        }
      }
    }
  }

  return filtros;
}
