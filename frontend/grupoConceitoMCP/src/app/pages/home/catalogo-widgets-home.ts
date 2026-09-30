import { Type } from '@angular/core';
import { WidgetAtalho } from '../../componentes/widget-atalho/widget-atalho';
import { WidgetChamadosPorStatus } from '../modulos/ti/home/widgets/widget-chamados-por-status/widget-chamados-por-status';
import { WidgetChamadosTotal } from '../modulos/ti/home/widgets/widget-chamados-total/widget-chamados-total';
import { WidgetIaCategoriaNaoCorrigida } from '../modulos/ti/home/widgets/widget-ia-categoria-nao-corrigida/widget-ia-categoria-nao-corrigida';
import { WidgetIaChamadosAvaliados } from '../modulos/ti/home/widgets/widget-ia-chamados-avaliados/widget-ia-chamados-avaliados';
import { WidgetIaChamadosEscalados } from '../modulos/ti/home/widgets/widget-ia-chamados-escalados/widget-ia-chamados-escalados';
import { WidgetIaTokensHoje } from '../modulos/ti/home/widgets/widget-ia-tokens-hoje/widget-ia-tokens-hoje';
import { WidgetSegurancaAchadosAtivos } from '../modulos/ti/home/widgets/widget-seguranca-achados-ativos/widget-seguranca-achados-ativos';
import { WidgetFaturamentoTotal } from '../modulos/financeiro/home/widgets/widget-faturamento-total/widget-faturamento-total';
import { WidgetSaldoProjetado } from '../modulos/financeiro/home/widgets/widget-saldo-projetado/widget-saldo-projetado';

export type TamanhoWidgetHome = 'pequeno' | 'grande';

/** Item do layout salvo — id JÁ namespaced (`"<modulo>:<id>"` ou
 * `"comum:<id>"`, mesmo formato do backend, ver `server/home/dashboard.py`). */
export interface ItemLayoutHome {
  id: string;
  tamanho: TamanhoWidgetHome;
}

/** Props estáticas de um widget do tipo atalho (ver `WidgetAtalho`) — o
 * próprio catálogo já carrega o conteúdo pronto, passado via
 * `NgComponentOutletInputs` (ver `home.html`), porque não há dado nenhum
 * pra buscar. */
export interface PropsWidgetAtalho {
  titulo: string;
  texto: string;
  iconeSvg: string;
  rota?: string;
  href?: string;
}

export interface DefinicaoWidgetHome {
  id: string;
  titulo: string;
  /** Módulo dono do widget (`sessao.modulos()`) — controla quem VÊ este
   * widget no catálogo, junto de `disponibilidadeDev`/`exigeAdministrador`.
   * `null` = widget COMUM, sem módulo dono — disponível pra qualquer
   * usuário autenticado (ex: "Central de suporte"). */
  modulo: string | null;
  /** `true` = só aparece no catálogo pra quem `sessao.ehDesenvolvedor()`,
   * além de já ter acesso ao `modulo` (quando houver). */
  disponibilidadeDev: boolean;
  /** `true` = só aparece no catálogo pra quem `sessao.administrador()`
   * (qualquer papel admin, não um módulo específico — ex: "Usuários"). */
  exigeAdministrador: boolean;
  tamanhoPadrao: TamanhoWidgetHome;
  /** Componente renderizado via `NgComponentOutlet` (ver `home.html`) — um
   * widget novo só precisa somar uma entrada aqui, nada muda em `home.ts`. */
  componente: Type<unknown>;
  /** Só widget do tipo atalho (`componente: WidgetAtalho`) usa isso — vira
   * `NgComponentOutletInputs`. Widget de indicador busca o próprio dado,
   * sem receber nada de fora. */
  props?: PropsWidgetAtalho;
}

function atalho(
  id: string,
  modulo: string | null,
  props: PropsWidgetAtalho,
  opcoes: { exigeAdministrador?: boolean } = {},
): DefinicaoWidgetHome {
  return {
    id,
    titulo: props.titulo,
    modulo,
    disponibilidadeDev: false,
    exigeAdministrador: opcoes.exigeAdministrador ?? false,
    tamanhoPadrao: 'pequeno',
    componente: WidgetAtalho,
    props,
  };
}

/** Catálogo UNIFICADO — união namespaced dos catálogos de cada módulo
 * (TI, Financeiro, RH; Estoque entra quando tiver indicador de verdade pra
 * mostrar) MAIS o catálogo COMUM (sem módulo dono). Ids precisam ficar em
 * sincronia com `server/ti/dashboard_widgets.py`,
 * `server/financeiro/dashboard_widgets.py`, `server/rh/dashboard_widgets.py`
 * e `server/home/dashboard_widgets_comuns.py` — mesmo tipo de duplicação de
 * string entre back/front já aceito no projeto (ex: módulos conhecidos).
 *
 * Todo widget — indicador de dado OU atalho de navegação — é uma entrada
 * igual às outras aqui; a única diferença é o `componente` (um busca o
 * próprio dado, o outro só recebe `props` estáticas prontas). */
export const CATALOGO_WIDGETS_HOME: DefinicaoWidgetHome[] = [
  // --- TI: indicadores de dado ---
  {
    id: 'ti:chamados_total',
    titulo: 'Chamados em aberto',
    modulo: 'ti',
    disponibilidadeDev: false,
    exigeAdministrador: false,
    tamanhoPadrao: 'pequeno',
    componente: WidgetChamadosTotal,
  },
  {
    id: 'ti:chamados_por_status',
    titulo: 'Chamados por status',
    modulo: 'ti',
    disponibilidadeDev: false,
    exigeAdministrador: false,
    tamanhoPadrao: 'grande',
    componente: WidgetChamadosPorStatus,
  },
  {
    id: 'ti:ia_tokens_hoje',
    titulo: 'Tokens hoje',
    modulo: 'ti',
    disponibilidadeDev: true,
    exigeAdministrador: false,
    tamanhoPadrao: 'pequeno',
    componente: WidgetIaTokensHoje,
  },
  {
    id: 'ti:ia_chamados_avaliados',
    titulo: 'Chamados avaliados pela IA (30d)',
    modulo: 'ti',
    disponibilidadeDev: true,
    exigeAdministrador: false,
    tamanhoPadrao: 'pequeno',
    componente: WidgetIaChamadosAvaliados,
  },
  {
    id: 'ti:ia_chamados_escalados',
    titulo: 'Escalados pra humano (30d)',
    modulo: 'ti',
    disponibilidadeDev: true,
    exigeAdministrador: false,
    tamanhoPadrao: 'pequeno',
    componente: WidgetIaChamadosEscalados,
  },
  {
    id: 'ti:ia_categoria_nao_corrigida',
    titulo: 'Categoria não corrigida automaticamente (30d)',
    modulo: 'ti',
    disponibilidadeDev: true,
    exigeAdministrador: false,
    tamanhoPadrao: 'pequeno',
    componente: WidgetIaCategoriaNaoCorrigida,
  },
  {
    id: 'ti:seguranca_achados_ativos',
    titulo: 'Achados de segurança ativos',
    modulo: 'ti',
    disponibilidadeDev: false,
    exigeAdministrador: false,
    tamanhoPadrao: 'pequeno',
    componente: WidgetSegurancaAchadosAtivos,
  },

  // --- TI: atalhos ---
  atalho('ti:seguranca', 'ti', {
    titulo: 'Segurança de TI',
    texto:
      'A IA analisa padrão de login e volume de acesso a dado recente e aponta possível tentativa de invasão ou acesso suspeito.',
    rota: '/ti/seguranca',
    iconeSvg: `<path d="M12 3l7 3v6c0 5-3.5 8-7 9-3.5-1-7-4-7-9V6l7-3Z" stroke-linecap="round" stroke-linejoin="round" /><path d="M12 8v5M12 16.5h.01" stroke-linecap="round" />`,
  }),
  atalho('ti:auditoria_chamados', 'ti', {
    titulo: 'Auditoria de Chamados',
    texto:
      'A IA audita cada chamado novo do GLPI e só libera pra fila de atendimento quando tem informação suficiente.',
    rota: '/ti/chamados',
    iconeSvg: `<path d="M4 5h16v11H8l-4 4V5Z" stroke-linecap="round" stroke-linejoin="round" /><path d="M8 10h8M8 13h5" stroke-linecap="round" />`,
  }),

  // --- Financeiro: indicadores de dado ---
  {
    id: 'financeiro:saldo_projetado',
    titulo: 'Saldo projetado (a receber - a pagar)',
    modulo: 'financeiro',
    disponibilidadeDev: false,
    exigeAdministrador: false,
    tamanhoPadrao: 'pequeno',
    componente: WidgetSaldoProjetado,
  },
  {
    id: 'financeiro:faturamento_total',
    titulo: 'Faturamento total (últimos 12 meses)',
    modulo: 'financeiro',
    disponibilidadeDev: false,
    exigeAdministrador: false,
    tamanhoPadrao: 'pequeno',
    componente: WidgetFaturamentoTotal,
  },

  // --- Financeiro: atalhos ---
  atalho('financeiro:modulos_financeiros', 'financeiro', {
    titulo: 'Módulos financeiros',
    texto: 'Relatórios financeiros específicos do Grupo Conceito.',
    rota: '/financeiro/especifico-grupo-conceito',
    iconeSvg: `<rect x="3" y="6" width="18" height="13" rx="2" /><path d="M3 10h18M8 6V4h8v2" stroke-linecap="round" />`,
  }),
  atalho('financeiro:criar_relatorio', 'financeiro', {
    titulo: 'Criar relatório',
    texto: 'Monte seu próprio relatório escolhendo tabela, colunas e filtros.',
    rota: '/financeiro/criar-relatorio',
    iconeSvg: `<rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 10h18M9 10v10" stroke-linecap="round" />`,
  }),
  atalho('financeiro:assistente_ia', 'financeiro', {
    titulo: 'Assistente IA',
    texto: 'Peça relatórios em linguagem natural e baixe o resultado em Excel na hora.',
    rota: '/financeiro/chat',
    iconeSvg: `<path d="M4 5h16v11H8l-4 4V5Z" stroke-linecap="round" stroke-linejoin="round" />`,
  }),
  atalho('financeiro:historico_relatorios', 'financeiro', {
    titulo: 'Histórico de relatórios',
    texto: 'Veja, baixe ou fixe relatórios já gerados pelo assistente.',
    rota: '/relatorios/historico',
    iconeSvg: `<path d="M12 8v4l3 3" stroke-linecap="round" stroke-linejoin="round" /><circle cx="12" cy="12" r="9" />`,
  }),

  // --- RH: atalhos (sem indicador de dado ainda — nenhuma métrica candidata definida) ---
  atalho('rh:analise_candidato', 'rh', {
    titulo: 'Análise de Candidato',
    texto:
      'Suba currículos pro pool de candidatos ativos, ou descreva uma vaga pra IA buscar quem encaixa melhor.',
    rota: '/rh/analise-candidato',
    iconeSvg: `<path d="M9 12h6M9 16h6M9 8h2" stroke-linecap="round" /><path d="M7 3h7l4 4v14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" stroke-linejoin="round" />`,
  }),
  atalho('rh:repescagem', 'rh', {
    titulo: 'Repescagem',
    texto:
      'Candidatos já dispensados — reconsidere pra uma vaga nova navegando na lista ou pedindo pra IA buscar entre eles.',
    rota: '/rh/repescagem',
    iconeSvg: `<path d="M4 4v6h6" stroke-linecap="round" stroke-linejoin="round" /><path d="M20 20v-6h-6" stroke-linecap="round" stroke-linejoin="round" /><path d="M5.5 15a7 7 0 0 0 12.3 2.5M18.5 9a7 7 0 0 0-12.3-2.5" stroke-linecap="round" />`,
  }),
  atalho('rh:colaboradores', 'rh', {
    titulo: 'Colaboradores',
    texto: 'Consulte o pool de candidatos já contratados, separado dos que ainda estão em avaliação.',
    rota: '/rh/colaboradores',
    iconeSvg: `<circle cx="9" cy="8" r="3.2" /><path d="M3.5 19c0-3 2.5-5.2 5.5-5.2s5.5 2.2 5.5 5.2" stroke-linecap="round" /><path d="m15 13 2 2 4-4" stroke-linecap="round" stroke-linejoin="round" />`,
  }),

  // --- Comuns: sem módulo dono, liberado pra qualquer usuário autenticado ---
  atalho('comum:central_suporte', null, {
    titulo: 'Central de suporte',
    texto: 'Encontrou um bug ou está com dificuldade? Abra um chamado com o time de TI.',
    href: 'https://suporte.grupoconceito.com/front/central.php',
    iconeSvg: `<circle cx="12" cy="12" r="9" /><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .9-1 1.7v.3" stroke-linecap="round" stroke-linejoin="round" /><circle cx="12" cy="17" r="0.15" fill="currentColor" stroke-width="2.4" />`,
  }),
  atalho(
    'comum:usuarios',
    null,
    {
      titulo: 'Usuários',
      texto: 'Cadastre e gerencie os usuários com acesso ao sistema.',
      rota: '/usuarios',
      iconeSvg: `<circle cx="9" cy="8" r="3.2" /><path d="M3.5 19c0-3 2.5-5.2 5.5-5.2s5.5 2.2 5.5 5.2" stroke-linecap="round" /><path d="M16 9.5a2.7 2.7 0 1 0 0-5.4M18.5 19c0-2.4-1.7-4.4-4-5" stroke-linecap="round" />`,
    },
    { exigeAdministrador: true },
  ),
];

export function idWidgetHomeValido(id: string): boolean {
  return CATALOGO_WIDGETS_HOME.some((definicao) => definicao.id === id);
}

export function definicaoWidgetHome(id: string): DefinicaoWidgetHome | undefined {
  return CATALOGO_WIDGETS_HOME.find((definicao) => definicao.id === id);
}
