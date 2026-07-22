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
  /**
   * Só usado quando tipo === 'select' e `opcoes` não é informado — sufixo da
   * rota REST do backend (/api/financeiro/{apiEndpoint}) que devolve as
   * opções já cadastradas no banco (ex: clientes, vendedores).
   */
  apiEndpoint?: string;
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
      {
        nome: 'Duplicata Mercantil em Lote',
        apiEndpoint: 'duplicata-mercantil',
        filtros: [
          { chave: 'cliente', rotulo: 'Cliente', tipo: 'select', apiEndpoint: 'clientes' },
          { chave: 'loja', rotulo: 'Loja', tipo: 'select', apiEndpoint: 'lojas' },
          { chave: 'vencto', rotulo: 'Vencimento', tipo: 'periodo-data' },
          { chave: 'prefixo', rotulo: 'Prefixo', tipo: 'select', apiEndpoint: 'prefixos' },
          { chave: 'tipo', rotulo: 'Tipo', tipo: 'select', apiEndpoint: 'tipos' },
          { chave: 'vendedor', rotulo: 'Consultor', tipo: 'select', apiEndpoint: 'vendedores' },
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
      {
        nome: 'Relatório Baixa por Produtos',
        apiEndpoint: 'baixa-produtos',
        filtros: [
          { chave: 'titulo_ini', rotulo: 'Título De', tipo: 'texto' },
          { chave: 'titulo_fim', rotulo: 'Título Até', tipo: 'texto' },
          { chave: 'produto_ini', rotulo: 'Produto De', tipo: 'select', apiEndpoint: 'produtos' },
          { chave: 'produto_fim', rotulo: 'Produto Até', tipo: 'select', apiEndpoint: 'produtos' },
          { chave: 'data_baixa', rotulo: 'Data da Baixa', tipo: 'periodo-data' }
        ]
      },
      {
        nome: 'Contas a Receber com Descrição do Produto',
        apiEndpoint: 'contas-receber-produto',
        filtros: [
          { chave: 'cliente', rotulo: 'Cliente', tipo: 'select', apiEndpoint: 'clientes' },
          { chave: 'emissao', rotulo: 'Emissão', tipo: 'periodo-data' },
          { chave: 'vencimento', rotulo: 'Vencimento', tipo: 'periodo-data' },
          { chave: 'tipos_excluir', rotulo: 'Tipos a não considerar (separe por ;)', tipo: 'texto' }
        ]
      },
      {
        nome: 'FINR10 - Posição dos Títulos',
        apiEndpoint: 'posicao-titulos',
        filtros: [
          { chave: 'cliente_ini', rotulo: 'Cliente De', tipo: 'select', apiEndpoint: 'clientes' },
          { chave: 'cliente_fim', rotulo: 'Cliente Até', tipo: 'select', apiEndpoint: 'clientes' },
          { chave: 'prefixo_ini', rotulo: 'Prefixo De', tipo: 'select', apiEndpoint: 'prefixos' },
          { chave: 'prefixo_fim', rotulo: 'Prefixo Até', tipo: 'select', apiEndpoint: 'prefixos' },
          { chave: 'titulo_ini', rotulo: 'Título De', tipo: 'texto' },
          { chave: 'titulo_fim', rotulo: 'Título Até', tipo: 'texto' },
          { chave: 'banco_ini', rotulo: 'Banco De', tipo: 'texto' },
          { chave: 'banco_fim', rotulo: 'Banco Até', tipo: 'texto' },
          { chave: 'natureza_ini', rotulo: 'Natureza De', tipo: 'select', apiEndpoint: 'naturezas' },
          { chave: 'natureza_fim', rotulo: 'Natureza Até', tipo: 'select', apiEndpoint: 'naturezas' },
          { chave: 'loja_ini', rotulo: 'Loja De', tipo: 'select', apiEndpoint: 'lojas' },
          { chave: 'loja_fim', rotulo: 'Loja Até', tipo: 'select', apiEndpoint: 'lojas' },
          { chave: 'vencimento', rotulo: 'Vencimento', tipo: 'periodo-data' },
          { chave: 'emissao', rotulo: 'Emissão', tipo: 'periodo-data' },
          {
            chave: 'saldo_retroativo',
            rotulo: 'Saldo Retroativo',
            tipo: 'select',
            opcoes: [
              { valor: '', rotulo: 'Não' },
              { valor: '1', rotulo: 'Sim' }
            ]
          },
          {
            chave: 'considerar_excluidos',
            rotulo: 'Considerar Excluídos',
            tipo: 'select',
            opcoes: [
              { valor: '', rotulo: 'Não' },
              { valor: '1', rotulo: 'Sim' }
            ]
          },
          {
            chave: 'abatimentos',
            rotulo: 'Abatimentos',
            tipo: 'select',
            opcoes: [
              { valor: '1', rotulo: 'Lista' },
              { valor: '2', rotulo: 'Não lista' },
              { valor: '3', rotulo: 'Despreza' }
            ]
          },
          {
            chave: 'ordenar_por',
            rotulo: 'Ordenar por',
            tipo: 'select',
            opcoes: [
              { valor: 'cliente', rotulo: 'Cliente' },
              { valor: 'numero', rotulo: 'Número' },
              { valor: 'vencimento', rotulo: 'Vencimento' },
              { valor: 'natureza', rotulo: 'Natureza' },
              { valor: 'banco', rotulo: 'Banco' }
            ]
          }
        ]
      },
      {
        nome: 'FINR137 - Posição dos Títulos a Receber por Vendedor',
        apiEndpoint: 'posicao-titulos-vendedor',
        filtros: [
          { chave: 'cliente_ini', rotulo: 'Cliente De', tipo: 'select', apiEndpoint: 'clientes' },
          { chave: 'cliente_fim', rotulo: 'Cliente Até', tipo: 'select', apiEndpoint: 'clientes' },
          { chave: 'loja_ini', rotulo: 'Loja De', tipo: 'select', apiEndpoint: 'lojas' },
          { chave: 'loja_fim', rotulo: 'Loja Até', tipo: 'select', apiEndpoint: 'lojas' },
          { chave: 'vendedor_ini', rotulo: 'Vendedor De', tipo: 'select', apiEndpoint: 'vendedores' },
          { chave: 'vendedor_fim', rotulo: 'Vendedor Até', tipo: 'select', apiEndpoint: 'vendedores' },
          { chave: 'emissao', rotulo: 'Emissão', tipo: 'periodo-data' },
          { chave: 'vencimento', rotulo: 'Vencimento', tipo: 'periodo-data' },
          { chave: 'tipos_incluir', rotulo: 'Tipos a considerar (separe por ;)', tipo: 'texto' },
          { chave: 'tipos_excluir', rotulo: 'Tipos a não considerar (separe por ;)', tipo: 'texto' },
          {
            chave: 'saldo_retroativo',
            rotulo: 'Saldo Retroativo',
            tipo: 'select',
            opcoes: [
              { valor: '', rotulo: 'Não' },
              { valor: '1', rotulo: 'Sim' }
            ]
          }
        ]
      },
      {
        nome: 'FINR11 - Posição dos Títulos a Pagar',
        apiEndpoint: 'posicao-titulos-pagar',
        filtros: [
          { chave: 'fornecedor_ini', rotulo: 'Fornecedor De', tipo: 'select', apiEndpoint: 'fornecedores' },
          { chave: 'fornecedor_fim', rotulo: 'Fornecedor Até', tipo: 'select', apiEndpoint: 'fornecedores' },
          { chave: 'prefixo_ini', rotulo: 'Prefixo De', tipo: 'select', apiEndpoint: 'prefixos' },
          { chave: 'prefixo_fim', rotulo: 'Prefixo Até', tipo: 'select', apiEndpoint: 'prefixos' },
          { chave: 'titulo_ini', rotulo: 'Título De', tipo: 'texto' },
          { chave: 'titulo_fim', rotulo: 'Título Até', tipo: 'texto' },
          { chave: 'banco_ini', rotulo: 'Banco De', tipo: 'texto' },
          { chave: 'banco_fim', rotulo: 'Banco Até', tipo: 'texto' },
          { chave: 'natureza_ini', rotulo: 'Natureza De', tipo: 'select', apiEndpoint: 'naturezas' },
          { chave: 'natureza_fim', rotulo: 'Natureza Até', tipo: 'select', apiEndpoint: 'naturezas' },
          { chave: 'loja_ini', rotulo: 'Loja De', tipo: 'select', apiEndpoint: 'lojas' },
          { chave: 'loja_fim', rotulo: 'Loja Até', tipo: 'select', apiEndpoint: 'lojas' },
          { chave: 'vencimento', rotulo: 'Vencimento', tipo: 'periodo-data' },
          { chave: 'emissao', rotulo: 'Emissão', tipo: 'periodo-data' },
          {
            chave: 'saldo_retroativo',
            rotulo: 'Saldo Retroativo',
            tipo: 'select',
            opcoes: [
              { valor: '', rotulo: 'Não' },
              { valor: '1', rotulo: 'Sim' }
            ]
          },
          {
            chave: 'considerar_excluidos',
            rotulo: 'Considerar Excluídos',
            tipo: 'select',
            opcoes: [
              { valor: '', rotulo: 'Não' },
              { valor: '1', rotulo: 'Sim' }
            ]
          },
          {
            chave: 'abatimentos',
            rotulo: 'Abatimentos',
            tipo: 'select',
            opcoes: [
              { valor: '1', rotulo: 'Lista' },
              { valor: '2', rotulo: 'Não lista' },
              { valor: '3', rotulo: 'Despreza' }
            ]
          },
          {
            chave: 'ordenar_por',
            rotulo: 'Ordenar por',
            tipo: 'select',
            opcoes: [
              { valor: 'fornecedor', rotulo: 'Fornecedor' },
              { valor: 'numero', rotulo: 'Número' },
              { valor: 'vencimento', rotulo: 'Vencimento' },
              { valor: 'natureza', rotulo: 'Natureza' },
              { valor: 'banco', rotulo: 'Banco' }
            ]
          }
        ]
      },
      {
        nome: 'FINR12 - Relação de Baixas',
        apiEndpoint: 'relacao-baixas',
        filtros: [
          {
            chave: 'tipo_movimento',
            rotulo: 'Tipo',
            tipo: 'select',
            obrigatorio: true,
            opcoes: [
              { valor: 'R', rotulo: 'Recebimentos' },
              { valor: 'P', rotulo: 'Pagamentos' }
            ]
          },
          { chave: 'data_baixa', rotulo: 'Data da Baixa', tipo: 'periodo-data', obrigatorio: true },
          { chave: 'banco_ini', rotulo: 'Banco De', tipo: 'texto' },
          { chave: 'banco_fim', rotulo: 'Banco Até', tipo: 'texto' },
          { chave: 'natureza_ini', rotulo: 'Natureza De', tipo: 'select', apiEndpoint: 'naturezas' },
          { chave: 'natureza_fim', rotulo: 'Natureza Até', tipo: 'select', apiEndpoint: 'naturezas' },
          { chave: 'clifor_ini', rotulo: 'Cliente/Fornecedor De', tipo: 'texto' },
          { chave: 'clifor_fim', rotulo: 'Cliente/Fornecedor Até', tipo: 'texto' },
          { chave: 'prefixo_ini', rotulo: 'Prefixo De', tipo: 'select', apiEndpoint: 'prefixos' },
          { chave: 'prefixo_fim', rotulo: 'Prefixo Até', tipo: 'select', apiEndpoint: 'prefixos' },
          { chave: 'loja_ini', rotulo: 'Loja De', tipo: 'select', apiEndpoint: 'lojas' },
          { chave: 'loja_fim', rotulo: 'Loja Até', tipo: 'select', apiEndpoint: 'lojas' },
          { chave: 'lote_ini', rotulo: 'Lote De', tipo: 'texto' },
          { chave: 'lote_fim', rotulo: 'Lote Até', tipo: 'texto' },
          { chave: 'dt_digitacao', rotulo: 'Data de Digitação', tipo: 'periodo-data' },
          { chave: 'vencimento', rotulo: 'Vencimento do Título', tipo: 'periodo-data' },
          {
            chave: 'ordenar_por',
            rotulo: 'Ordenar por',
            tipo: 'select',
            opcoes: [
              { valor: 'data_baixa', rotulo: 'Data da Baixa' },
              { valor: 'banco', rotulo: 'Banco' },
              { valor: 'natureza', rotulo: 'Natureza' },
              { valor: 'clifor', rotulo: 'Cliente/Fornecedor' },
              { valor: 'numero', rotulo: 'Número do Título' },
              { valor: 'dt_digitacao', rotulo: 'Data de Digitação' },
              { valor: 'lote', rotulo: 'Lote' }
            ]
          }
        ]
      },
      {
        nome: 'FINR13 - Extrato Bancário',
        apiEndpoint: 'extrato-bancario',
        filtros: [
          { chave: 'conta_bancaria', rotulo: 'Conta Bancária', tipo: 'select', obrigatorio: true, apiEndpoint: 'contas-bancarias' },
          { chave: 'data', rotulo: 'Período', tipo: 'periodo-data', obrigatorio: true },
          {
            chave: 'saldo_tipo',
            rotulo: 'Exibir',
            tipo: 'select',
            opcoes: [
              { valor: '1', rotulo: 'Saldo Atual (todos)' },
              { valor: '2', rotulo: 'Somente Conciliados' },
              { valor: '3', rotulo: 'Somente Não Conciliados' }
            ]
          }
        ]
      },
      {
        nome: 'FINR14 - Relação de Títulos a Pagar com Retenção',
        apiEndpoint: 'retencao-impostos',
        filtros: [
          { chave: 'fornecedor_ini', rotulo: 'Fornecedor De', tipo: 'select', apiEndpoint: 'fornecedores' },
          { chave: 'fornecedor_fim', rotulo: 'Fornecedor Até', tipo: 'select', apiEndpoint: 'fornecedores' },
          { chave: 'loja_ini', rotulo: 'Loja De', tipo: 'select', apiEndpoint: 'lojas' },
          { chave: 'loja_fim', rotulo: 'Loja Até', tipo: 'select', apiEndpoint: 'lojas' },
          {
            chave: 'tipo_pessoa',
            rotulo: 'Tipo de Fornecedor',
            tipo: 'select',
            opcoes: [
              { valor: '', rotulo: 'Todos' },
              { valor: 'F', rotulo: 'Pessoa Física' },
              { valor: 'J', rotulo: 'Pessoa Jurídica' }
            ]
          },
          { chave: 'emissao', rotulo: 'Emissão', tipo: 'periodo-data' },
          { chave: 'vencimento', rotulo: 'Vencimento', tipo: 'periodo-data' },
          {
            chave: 'considera_impostos',
            rotulo: 'Impostos a Considerar',
            tipo: 'select',
            opcoes: [
              { valor: '1', rotulo: 'Somente Retido' },
              { valor: '2', rotulo: 'Retido + Calculado (Título em Aberto)' }
            ]
          },
          {
            chave: 'ordenar_por',
            rotulo: 'Ordenar Por',
            tipo: 'select',
            opcoes: [
              { valor: 'codigo', rotulo: 'Código do Fornecedor' },
              { valor: 'nome', rotulo: 'Nome do Fornecedor' }
            ]
          }
        ]
      },
      {
        nome: 'FIN32 - Movimento Financeiro Diário',
        apiEndpoint: 'movimento-financeiro-diario',
        filtros: [
          { chave: 'data', rotulo: 'Data de Referência', tipo: 'periodo-data', obrigatorio: true },
          {
            chave: 'considera_limite',
            rotulo: 'Considera Limite de Crédito',
            tipo: 'select',
            opcoes: [
              { valor: '2', rotulo: 'Não' },
              { valor: '1', rotulo: 'Sim' }
            ]
          }
        ]
      }
    ]
  }
];
