export type TipoFiltro = 'texto' | 'select' | 'periodo-data';

export interface OpcaoFiltro {
  valor: string;
  rotulo: string;
}

export interface CampoFiltro {
  /** Nome do parâmetro na URL (?chave=...). Em campos do tipo periodo-data, gera {chave}_ini e {chave}_fim. */
  chave: string;
  rotulo: string;
  tipo: TipoFiltro;
  obrigatorio?: boolean;
  /** Só usado quando tipo === 'select' — lista fixa de opções. */
  opcoes?: OpcaoFiltro[];
}

export interface RotinaFinanceira {
  nome: string;
  /** Sufixo da rota REST do backend: /api/financeiro/{apiEndpoint} */
  apiEndpoint?: string;
  /**
   * Filtros extras além da filial (que é sempre obrigatória, seleção múltipla,
   * e tratada à parte no painel — não precisa ser declarada aqui).
   */
  filtros?: CampoFiltro[];
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
      {
        nome: 'Fluxo de Caixa Realizado',
        apiEndpoint: 'fluxo-caixa-realizado',
        filtros: [{ chave: 'ano', rotulo: 'Ano', tipo: 'texto', obrigatorio: true }]
      },
      { nome: 'Boleto' },
      {
        nome: 'Duplicata Mercantil em Lote',
        apiEndpoint: 'duplicata-mercantil',
        filtros: [
          { chave: 'cliente', rotulo: 'Cliente', tipo: 'texto' },
          { chave: 'loja', rotulo: 'Loja', tipo: 'texto' },
          { chave: 'vencto', rotulo: 'Vencimento', tipo: 'periodo-data' },
          { chave: 'prefixo', rotulo: 'Prefixo', tipo: 'texto' },
          { chave: 'tipo', rotulo: 'Tipo', tipo: 'texto' },
          { chave: 'vendedor', rotulo: 'Consultor', tipo: 'texto' },
          {
            chave: 'status_assinatura',
            rotulo: 'Status assinatura',
            tipo: 'select',
            opcoes: [
              { valor: '', rotulo: 'Ambas' },
              { valor: '1', rotulo: 'Assinadas' },
              { valor: '2', rotulo: 'Não assinadas' }
            ]
          }
        ]
      },
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
