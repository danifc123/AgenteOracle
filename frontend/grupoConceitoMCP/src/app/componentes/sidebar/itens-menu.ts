export interface ItemMenu {
  rota: string;
  rotulo: string;
  /** Conteúdo interno do `<svg>` (paths/rects/circles), como HTML puro —
   * confiável porque vem só deste arquivo estático, nunca de dado externo. */
  iconeSvg: string;
  /** `true` só pro item que deve ficar "ativo" apenas na rota exata (ex:
   * visão geral de um módulo, que também é prefixo de outras rotas dele). */
  exato?: boolean;
}

export interface GrupoMenu {
  /** Bate com o nome do módulo em `sessao.modulos()` — controla se o grupo
   * aparece pro usuário logado. */
  chave: string;
  rotulo: string;
  iconeSvg: string;
  itens: ItemMenu[];
}

export const GRUPOS_MENU: GrupoMenu[] = [
  {
    chave: 'financeiro',
    rotulo: 'Financeiro',
    iconeSvg: `<rect x="3" y="6" width="18" height="13" rx="2" /><path d="M3 10h18M8 6V4h8v2" stroke-linecap="round" />`,
    itens: [
      {
        rota: '/financeiro/criar-relatorio',
        rotulo: 'Criar Relatório',
        iconeSvg: `<rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 10h18M9 10v10" stroke-linecap="round" />`,
      },
      {
        rota: '/financeiro/especifico-grupo-conceito',
        rotulo: 'Específico Grupo Conceito',
        iconeSvg: `<path d="M7 3h7l4 4v14H7V3Z" stroke-linecap="round" stroke-linejoin="round" /><path d="M14 3v4h4" stroke-linecap="round" stroke-linejoin="round" /><path d="M9.5 13h5M9.5 16.5h5" stroke-linecap="round" />`,
      },
      {
        rota: '/financeiro/fluxo-caixa',
        rotulo: 'Fluxo de Caixa',
        iconeSvg: `<rect x="3" y="6" width="18" height="13" rx="2" /><path d="M3 10h18" stroke-linecap="round" /><circle cx="8" cy="14.5" r="1.2" />`,
      },
      {
        rota: '/financeiro/vendas',
        rotulo: 'Vendas',
        iconeSvg: `<path d="M3 17 9 11l4 4 8-8" stroke-linecap="round" stroke-linejoin="round" /><path d="M15 7h6v6" stroke-linecap="round" stroke-linejoin="round" />`,
      },
      {
        rota: '/financeiro/chat',
        rotulo: 'Assistente IA',
        iconeSvg: `<path d="M4 5h16v11H8l-4 4V5Z" stroke-linecap="round" stroke-linejoin="round" />`,
      },
    ],
  },
  {
    chave: 'estoque',
    rotulo: 'Estoque',
    iconeSvg: `<path d="M4 8 12 3l8 5-8 5-8-5Z" stroke-linecap="round" stroke-linejoin="round" /><path d="M4 8v8l8 5 8-5V8" stroke-linecap="round" stroke-linejoin="round" /><path d="M12 13v8" stroke-linecap="round" />`,
    itens: [
      {
        rota: '/estoque',
        rotulo: 'Visão Geral',
        exato: true,
        iconeSvg: `<rect x="3" y="6" width="18" height="13" rx="2" /><path d="M3 10h18" stroke-linecap="round" /><circle cx="8" cy="14.5" r="1.2" />`,
      },
      {
        rota: '/estoque/criar-relatorio',
        rotulo: 'Criar Relatório',
        iconeSvg: `<rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 10h18M9 10v10" stroke-linecap="round" />`,
      },
      {
        rota: '/estoque/especifico-grupo-conceito',
        rotulo: 'Específico Grupo Conceito',
        iconeSvg: `<path d="M7 3h7l4 4v14H7V3Z" stroke-linecap="round" stroke-linejoin="round" /><path d="M14 3v4h4" stroke-linecap="round" stroke-linejoin="round" /><path d="M9.5 13h5M9.5 16.5h5" stroke-linecap="round" />`,
      },
      {
        rota: '/estoque/chat',
        rotulo: 'Assistente IA',
        iconeSvg: `<path d="M4 5h16v11H8l-4 4V5Z" stroke-linecap="round" stroke-linejoin="round" />`,
      },
    ],
  },
  {
    chave: 'rh',
    rotulo: 'RH',
    iconeSvg: `<circle cx="9" cy="8" r="3.2" /><path d="M3.5 19c0-3 2.5-5.2 5.5-5.2s5.5 2.2 5.5 5.2" stroke-linecap="round" /><path d="M15 4.5v4M17 6.5h-4" stroke-linecap="round" />`,
    itens: [
      {
        rota: '/rh/analise-candidato',
        rotulo: 'Análise de Candidato',
        iconeSvg: `<path d="M9 12h6M9 16h6M9 8h2" stroke-linecap="round" /><path d="M7 3h7l4 4v14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" stroke-linejoin="round" />`,
      },
      {
        rota: '/rh/selecionar-candidato',
        rotulo: 'Selecionar Candidato',
        iconeSvg: `<circle cx="11" cy="11" r="6.5" /><path d="m20 20-3.8-3.8" stroke-linecap="round" />`,
      },
    ],
  },
  {
    chave: 'ti',
    rotulo: 'TI',
    iconeSvg: `<rect x="3" y="4" width="18" height="12" rx="2" /><path d="M8 20h8M12 16v4" stroke-linecap="round" />`,
    itens: [
      {
        rota: '/ti/seguranca',
        rotulo: 'Segurança de TI',
        iconeSvg: `<path d="M12 3l7 3v6c0 5-3.5 8-7 9-3.5-1-7-4-7-9V6l7-3Z" stroke-linecap="round" stroke-linejoin="round" /><path d="M12 8v5M12 16.5h.01" stroke-linecap="round" />`,
      },
    ],
  },
];
