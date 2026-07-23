/** Espelha o registro de views financeiras do backend
 * (agent/financeiro/schema.py) — servido em GET /api/financeiro/relatorio/views
 * e usado pela tela "Criar Relatório" pra listar tabelas/colunas disponíveis
 * e resolver quais podem ser combinadas num mesmo relatório. */

export interface ColunaView {
  nome: string;
  descricao: string;
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
