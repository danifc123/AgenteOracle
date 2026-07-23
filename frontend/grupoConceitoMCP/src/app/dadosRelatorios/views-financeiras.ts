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

export interface ViewFinanceira {
  nome: string;
  descricao: string;
  colunas: ColunaView[];
  relacionamentos: RelacionamentoView[];
}
