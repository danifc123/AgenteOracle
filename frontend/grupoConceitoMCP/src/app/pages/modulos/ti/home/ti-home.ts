import { CdkDrag, CdkDragDrop, CdkDragHandle, CdkDropList, moveItemInArray } from '@angular/cdk/drag-drop';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { Dialog } from '../../../../componentes/dialog/dialog';
import { AtalhoModulo, HomeModulo } from '../../../../componentes/home-modulo/home-modulo';
import { LayoutDashboardTi } from '../../../../servicos/layout-dashboard-ti/layout-dashboard-ti';
import { Sessao } from '../../../../servicos/sessao/sessao';
import { UsoIa } from '../../../../servicos/uso-ia/uso-ia';
import { CATALOGO_WIDGETS_TI, IdWidgetTi, ItemLayoutTi, definicaoWidgetTi, idWidgetTiValido } from './widgets/catalogo-widgets-ti';
import { WidgetChamadosPorStatus } from './widgets/widget-chamados-por-status/widget-chamados-por-status';
import { WidgetChamadosTotal } from './widgets/widget-chamados-total/widget-chamados-total';
import { WidgetIaCategoriaNaoCorrigida } from './widgets/widget-ia-categoria-nao-corrigida/widget-ia-categoria-nao-corrigida';
import { WidgetIaChamadosAvaliados } from './widgets/widget-ia-chamados-avaliados/widget-ia-chamados-avaliados';
import { WidgetIaChamadosEscalados } from './widgets/widget-ia-chamados-escalados/widget-ia-chamados-escalados';
import { WidgetIaTokensHoje } from './widgets/widget-ia-tokens-hoje/widget-ia-tokens-hoje';
import { WidgetSegurancaAchadosAtivos } from './widgets/widget-seguranca-achados-ativos/widget-seguranca-achados-ativos';

const ATALHOS: AtalhoModulo[] = [
  {
    titulo: 'Segurança de TI',
    texto:
      'A IA analisa padrão de login e volume de acesso a dado recente e aponta possível tentativa de invasão ou acesso suspeito.',
    rota: '/ti/seguranca',
    iconeSvg: `<path d="M12 3l7 3v6c0 5-3.5 8-7 9-3.5-1-7-4-7-9V6l7-3Z" stroke-linecap="round" stroke-linejoin="round" /><path d="M12 8v5M12 16.5h.01" stroke-linecap="round" />`,
  },
  {
    titulo: 'Auditoria de Chamados',
    texto:
      'A IA audita cada chamado novo do GLPI e só libera pra fila de atendimento quando tem informação suficiente.',
    rota: '/ti/chamados',
    iconeSvg: `<path d="M4 5h16v11H8l-4 4V5Z" stroke-linecap="round" stroke-linejoin="round" /><path d="M8 10h8M8 13h5" stroke-linecap="round" />`,
  },
  {
    titulo: 'Central de suporte',
    texto: 'Encontrou um bug ou está com dificuldade? Abra um chamado no GLPI.',
    href: 'https://suporte.grupoconceito.com/front/central.php',
    iconeSvg: `<circle cx="12" cy="12" r="9" /><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .9-1 1.7v.3" stroke-linecap="round" stroke-linejoin="round" /><circle cx="12" cy="17" r="0.15" fill="currentColor" stroke-width="2.4" />`,
  },
];

// Consumo de IA muda sozinho (poller de chamados a cada 5 min, chamadas
// reais do dia a dia) — sem isso, quem deixa a aba aberta só vê o número
// congelado do momento em que entrou, precisando dar F5 pra atualizar.
const INTERVALO_ATUALIZACAO_USO_IA_MS = 30_000;

/** Home do time de TI — mostrada em `/` pra quem só tem o módulo TI
 * liberado, e pra desenvolvedor quando troca pro TI no seletor do layout.
 * Mantém o hero + atalhos de sempre (`app-home-modulo`, casca
 * compartilhada com RH/Financeiro), fixos, sempre primeiro.
 *
 * Abaixo, uma grade de INDICADORES personalizável por usuário (2026-09):
 * cada indicador é um componente autossuficiente (`widgets/widget-*`, cada
 * um busca seus próprios dados) — esta tela só sabe QUAIS ids mostrar, EM
 * QUE ORDEM e EM QUE TAMANHO (`LayoutDashboardTi`, persistido no backend
 * por usuário), não como cada um funciona por dentro. Os indicadores de IA
 * (`ia_*`) exigem `sessao.ehDesenvolvedor()` — o polling de `UsoIa`
 * continua orquestrado aqui (não em cada widget), senão vários widgets de
 * IA abertos ao mesmo tempo disparariam requests redundantes. */
@Component({
  selector: 'app-ti-home',
  imports: [
    CdkDrag,
    CdkDragHandle,
    CdkDropList,
    Dialog,
    HomeModulo,
    WidgetChamadosPorStatus,
    WidgetChamadosTotal,
    WidgetIaCategoriaNaoCorrigida,
    WidgetIaChamadosAvaliados,
    WidgetIaChamadosEscalados,
    WidgetIaTokensHoje,
    WidgetSegurancaAchadosAtivos,
  ],
  templateUrl: './ti-home.html',
  styleUrl: './ti-home.scss',
})
export class TiHome {
  protected readonly sessao = inject(Sessao);
  protected readonly usoIa = inject(UsoIa);
  protected readonly layoutDashboard = inject(LayoutDashboardTi);

  protected readonly atalhos = ATALHOS;
  protected readonly modoEdicao = signal(false);
  protected readonly catalogoAberto = signal(false);

  // Defesa em profundidade: o backend já filtra id desconhecido, id que
  // exige desenvolvedor e tamanho inválido antes de devolver o layout
  // (`server/ti/dashboard.py::_layout_visivel`), mas essa tela não confia
  // só nisso — um layout salvo/cacheado de outra sessão (ex: alguém que
  // deixou de ser desenvolvedor) nunca deveria renderizar um indicador de
  // IA aqui.
  protected readonly widgetsVisiveis = computed<ItemLayoutTi[]>(() => {
    const ehDev = this.sessao.ehDesenvolvedor();
    return this.layoutDashboard.widgets().filter((item): item is ItemLayoutTi => {
      if (!idWidgetTiValido(item.id)) {
        return false;
      }
      const definicao = definicaoWidgetTi(item.id);
      return !definicao.disponibilidadeDev || ehDev;
    });
  });

  protected readonly catalogoDisponivel = computed(() => {
    const jaVisiveis = new Set(this.widgetsVisiveis().map((item) => item.id));
    return CATALOGO_WIDGETS_TI.filter(
      (definicao) =>
        (!definicao.disponibilidadeDev || this.sessao.ehDesenvolvedor()) && !jaVisiveis.has(definicao.id),
    );
  });

  constructor() {
    this.layoutDashboard.carregar();
    if (this.sessao.ehDesenvolvedor()) {
      this.usoIa.carregar();
      const intervalo = setInterval(() => this.usoIa.carregar(), INTERVALO_ATUALIZACAO_USO_IA_MS);
      inject(DestroyRef).onDestroy(() => clearInterval(intervalo));
    }
  }

  protected onSoltar(evento: CdkDragDrop<ItemLayoutTi[]>): void {
    const widgets = [...this.widgetsVisiveis()];
    moveItemInArray(widgets, evento.previousIndex, evento.currentIndex);
    this.layoutDashboard.agendarSalvar(widgets);
  }

  // Diálogo fica aberto depois de adicionar de propósito — permite
  // escolher vários indicadores em sequência sem reabrir o diálogo a cada
  // um (fecha só quando o usuário clica em Fechar/Esc/fora).
  protected adicionarWidget(id: IdWidgetTi): void {
    this.layoutDashboard.salvarAgora([...this.widgetsVisiveis(), { id, tamanho: definicaoWidgetTi(id).tamanhoPadrao }]);
  }

  protected removerWidget(id: IdWidgetTi): void {
    this.layoutDashboard.salvarAgora(this.widgetsVisiveis().filter((item) => item.id !== id));
  }

  protected alternarTamanho(id: IdWidgetTi): void {
    const widgets = this.widgetsVisiveis().map((item) =>
      item.id === id ? { ...item, tamanho: item.tamanho === 'grande' ? ('pequeno' as const) : ('grande' as const) } : item,
    );
    this.layoutDashboard.salvarAgora(widgets);
  }
}
