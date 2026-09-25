/** Espelha o registro de views financeiras do backend
 * (agent/financeiro/schema.py) — servido em GET /api/financeiro/relatorio/views
 * e usado pela tela "Criar Relatório" pra listar tabelas/colunas disponíveis
 * e resolver quais podem ser combinadas num mesmo relatório. */

/** Decidido sempre pelo backend (`inferir_tipo_filtro`) — por padrão a
 * partir do nome da coluna, ou por override explícito (`ColunaView.tipo_filtro`
 * em schema.py) pra colunas onde a heurística por nome erraria. O front só
 * usa isso pra escolher o widget de filtro certo. "texto-numerico" (ex:
 * "nota") oferece os dois modos — lista de valores exatos E faixa
 * numérica, com um alternador na tela — porque a coluna é um código de
 * texto (zero-padded) mas o caso de uso mais comum é filtrar por
 * intervalo, não só valores avulsos. */
export type TipoFiltroColuna = 'texto' | 'numero' | 'periodo-data' | 'texto-numerico';

export interface ColunaView {
  nome: string;
  descricao: string;
  tipo: TipoFiltroColuna;
}

export interface RelacionamentoView {
  viewDestino: string;
  colunasLocais: string[];
  colunasDestino: string[];
  descricao: string;
}

/** De qual banco a view vem — "stage" (Oracle STAGE/SCIENCE_PROD) ou
 * "protheus" (Protheus HML). Views de fontes diferentes nunca podem ser
 * combinadas num mesmo relatório (ver `_fonte_comum` no backend) — são
 * bancos Oracle separados, sem `DB LINK` entre eles. */
export type FonteView = 'stage' | 'protheus';

export interface ViewFinanceira {
  nome: string;
  descricao: string;
  /** Opcional pra não obrigar todo placeholder/mock/teste que monta um
   * `ViewFinanceira` à mão a declarar isso — quem exibe agrupamento por
   * fonte trata ausência como 'stage' (ver `criar-relatorio.ts`). */
  fonte?: FonteView;
  colunas: ColunaView[];
  relacionamentos: RelacionamentoView[];
}
