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
    id: 'especifico-grupo-conceito',
    nome: 'Específico Grupo Conceito',
    descricao: 'Selecione a rotina de cadastro na lista abaixo',
    rotinas: [
      { nome: 'Fluxo de Caixa Realizado' },
      { nome: 'Boleto' },
      { nome: 'Duplicata Mercantil em Lote' },
      { nome: 'Assinar Dupl. em Lote' },
      { nome: 'Recibo' },
      { nome: 'Relatório Baixa por Produtos' },
      { nome: 'Manutenção de Provisionamento' },
      { nome: 'Contas a Receber com Descrição do Produto' },
      { nome: 'FINR10 - Posição dos Títulos' },
      { nome: 'FINR11 - Posição dos Títulos a Pagar' },
      { nome: 'FINR12 - Relação de Baixas' },
      { nome: 'FINR13 - Extrato Bancário' },
      { nome: 'FINR14 - Relação de Títulos a Pagar com Retenção' },
      { nome: 'FIN32 - Movimento Financeiro Diário' }
    ]
  }
];
