/** Rotinas de mentira pra tela "Específico Grupo Conceito" do Estoque —
 * mesmo formato de `modulos-financeiro.ts` (reaproveita os tipos de lá).
 * Nenhuma tem `apiEndpoint` ainda (não existe consulta SQL desse módulo),
 * então a tela mostra o mesmo placeholder "relatório ainda não disponível"
 * já usado no Financeiro pra rotinas sem backend. */

import { RotinaFinanceira } from './modulos-financeiro';

export const ROTINAS_ESTOQUE: RotinaFinanceira[] = [
  {
    nome: 'Movimentação de Estoque por Período',
    categoria: 'Movimentação',
    descricao: 'Entradas e saídas de estoque detalhadas, filtradas por produto e período.',
    filtros: [
      { chave: 'produto', rotulo: 'Produto', tipo: 'texto' },
      { chave: 'periodo', rotulo: 'Período', tipo: 'periodo-data' },
    ],
  },
  {
    nome: 'Posição de Suprimentos',
    categoria: 'Suprimentos',
    descricao: 'Níveis atuais de estoque por produto, com destaque pros itens abaixo do mínimo.',
    filtros: [
      { chave: 'produto', rotulo: 'Produto', tipo: 'texto' },
      {
        chave: 'status',
        rotulo: 'Status',
        tipo: 'select',
        opcoes: [
          { valor: '', rotulo: 'Todos' },
          { valor: 'ok', rotulo: 'OK' },
          { valor: 'baixo', rotulo: 'Baixo' },
          { valor: 'critico', rotulo: 'Crítico' },
        ],
      },
    ],
  },
  {
    nome: 'Entradas por Fornecedor',
    categoria: 'Entradas',
    descricao: 'Entradas de estoque agrupadas por fornecedor e período.',
    filtros: [
      { chave: 'fornecedor', rotulo: 'Fornecedor', tipo: 'texto' },
      { chave: 'periodo', rotulo: 'Período', tipo: 'periodo-data' },
    ],
  },
  {
    nome: 'Saídas por Requisitante',
    categoria: 'Saídas',
    descricao: 'Saídas de estoque agrupadas por requisitante (fazenda/setor) e período.',
    filtros: [
      { chave: 'requisitante', rotulo: 'Requisitante', tipo: 'texto' },
      { chave: 'periodo', rotulo: 'Período', tipo: 'periodo-data' },
    ],
  },
  {
    nome: 'Ajustes de Inventário',
    categoria: 'Movimentação',
    descricao: 'Ajustes manuais de quantidade em estoque (contagem, perda, avaria), por período.',
    filtros: [
      { chave: 'periodo', rotulo: 'Período', tipo: 'periodo-data' },
      {
        chave: 'motivo',
        rotulo: 'Motivo',
        tipo: 'select',
        opcoes: [
          { valor: '', rotulo: 'Todos' },
          { valor: 'contagem', rotulo: 'Contagem de inventário' },
          { valor: 'perda', rotulo: 'Perda' },
          { valor: 'avaria', rotulo: 'Avaria' },
        ],
      },
    ],
  },
];
