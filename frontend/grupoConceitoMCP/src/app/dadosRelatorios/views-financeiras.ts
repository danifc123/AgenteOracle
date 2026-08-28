/** Espelha o registro de views financeiras do backend
 * (agent/financeiro/schema.py) — servido em GET /api/financeiro/relatorio/views
 * e usado pela tela "Criar Relatório" pra listar tabelas/colunas disponíveis
 * e resolver quais podem ser combinadas num mesmo relatório. */

/** Decidido sempre pelo backend (`inferir_tipo_filtro`) a partir do nome da
 * coluna — o front só usa isso pra escolher o widget de filtro certo. */
export type TipoFiltroColuna = 'texto' | 'numero' | 'periodo-data';

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
