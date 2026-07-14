export interface RotinaFinanceira {
  nome: string;
  rota?: string;
}

export interface ModuloFinanceiroConfig {
  id: string;
  nome: string;
  descricao: string;
  rotinas: RotinaFinanceira[];
}

export const MODULOS_FINANCEIRO: ModuloFinanceiroConfig[] = [
  {
    id: 'cadastros',
    nome: 'Cadastros',
    descricao: 'Selecione a rotina de cadastro na lista abaixo',
    rotinas: [
      { nome: 'Ativos' },
      { nome: 'Apólices X Bens' },
      { nome: 'Planejamento de Provisão' },
      { nome: 'Apólices de Seguro' },
      { nome: 'Bens Em Terceiros' },
      { nome: 'Ficha do Ativo' },
      { nome: 'Demonstrativo Reavaliação' },
      { nome: 'Demonstrativo Ativo Fixo' },
      { nome: 'Demonstrativo Projeto de 12 Meses' },
      { nome: 'Responsáveis X Bens' },
      { nome: 'Demonstrativo de Realização de Projeto' }
    ]
  },
  {
    id: 'movimentos',
    nome: 'Movimentos',
    descricao: 'Selecione a rotina de cadastro na lista abaixo',
    rotinas: [
      { nome: 'Saldos a Depreciar' },
      { nome: 'Rateio de Despesa Por Ativo' },
      { nome: 'Razão Auxiliar' },
      { nome: 'Lançamentos Por Item Contábil' },
      { nome: 'Ampliações' },
      { nome: 'Valor Recuperável' },
      { nome: 'Processamento do Custo do Empréstimo' },
      { nome: 'Posição Valorizada' },
      { nome: 'Adiantamentos' },
      { nome: 'Movimentos' },
      { nome: 'Lançamentos Por Classe de Valor' },
      { nome: 'Demonstrativo de Bens de Terceiros' },
      { nome: 'Simulação do Valor Recuperável de Ativos' },
      { nome: 'Demonstrativo Depreciação do Projeto' },
      { nome: 'Resumo Por Conta' },
      { nome: 'Transferências' },
      { nome: 'Bens Depreciados' },
      { nome: 'Transferência de Locais' },
      { nome: 'Relatório Crédito de Pis/cofins Na Depreciação' },
      { nome: 'Provisão, Realizado e Avp - Projeto' },
      { nome: 'Posição Valorizada Na Data' },
      { nome: 'Aquisições' },
      { nome: 'Bens Depreciados Por %' },
      { nome: 'Inventário' },
      { nome: 'Correção Monetária' },
      { nome: 'Cálculo do Avp do Imobilizado' },
      { nome: 'Posição de 12 Meses' },
      { nome: 'Baixas' },
      { nome: 'Lançamentos Por Centro Custo' },
      { nome: 'Aquisição Por Transferência' },
      { nome: 'Simulação de Depreciação' },
      { nome: 'Custos de Empréstimos' }
    ]
  },
  {
    id: 'especifico-grupo-conceito',
    nome: 'Específico Grupo Conceito',
    descricao: 'Selecione a rotina de cadastro na lista abaixo',
    rotinas: [{ nome: 'Atfr04-listagem do Resumo Por Conta' }]
  }
];
