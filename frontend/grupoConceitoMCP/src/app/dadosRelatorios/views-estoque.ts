/** Tabelas de mentira pra tela "Criar Relatório" do Estoque — troca pra views
 * reais assim que existir a consulta SQL desse módulo (ver `estoque.ts`).
 * Mesmo formato de `views-financeiras.ts`, reaproveitado aqui. */

import { ViewFinanceira } from './views-financeiras';

export const MOCK_VIEWS_ESTOQUE: ViewFinanceira[] = [
  {
    nome: 'vw_movimentacao_estoque',
    descricao: 'Movimentações de entrada e saída de estoque, uma por lançamento.',
    colunas: [
      { nome: 'filial', descricao: 'código da filial', tipo: 'texto' },
      { nome: 'data', descricao: 'data da movimentação', tipo: 'periodo-data' },
      { nome: 'tipo', descricao: 'tipo do movimento (entrada ou saída)', tipo: 'texto' },
      { nome: 'produto_codigo', descricao: 'código do produto movimentado', tipo: 'texto' },
      { nome: 'quantidade', descricao: 'quantidade movimentada', tipo: 'numero' },
      { nome: 'documento', descricao: 'número do documento (NF/requisição)', tipo: 'texto' },
      { nome: 'fornecedor_codigo', descricao: 'código do fornecedor de origem (só em entradas)', tipo: 'texto' }
    ],
    relacionamentos: [
      {
        viewDestino: 'vw_produtos',
        colunasLocais: ['produto_codigo'],
        colunasDestino: ['codigo'],
        descricao: 'Descrição e níveis de estoque do produto movimentado.'
      },
      {
        viewDestino: 'vw_fornecedores',
        colunasLocais: ['fornecedor_codigo'],
        colunasDestino: ['codigo'],
        descricao: 'Fornecedor de origem, quando a movimentação é uma entrada.'
      }
    ]
  },
  {
    nome: 'vw_produtos',
    descricao: 'Cadastro de produtos e níveis de estoque atuais.',
    colunas: [
      { nome: 'codigo', descricao: 'código do produto', tipo: 'texto' },
      { nome: 'descricao', descricao: 'descrição do produto', tipo: 'texto' },
      { nome: 'estoque_atual', descricao: 'quantidade em estoque atualmente', tipo: 'numero' },
      { nome: 'estoque_minimo', descricao: 'quantidade mínima recomendada', tipo: 'numero' }
    ],
    relacionamentos: []
  },
  {
    nome: 'vw_fornecedores',
    descricao: 'Cadastro de fornecedores.',
    colunas: [
      { nome: 'codigo', descricao: 'código do fornecedor', tipo: 'texto' },
      { nome: 'nome', descricao: 'razão social', tipo: 'texto' },
      { nome: 'estado', descricao: 'sigla do estado (UF)', tipo: 'texto' }
    ],
    relacionamentos: []
  }
];
