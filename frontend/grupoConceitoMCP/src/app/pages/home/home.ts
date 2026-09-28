import { CdkDrag, CdkDragDrop, CdkDragHandle, CdkDropList, moveItemInArray } from '@angular/cdk/drag-drop';
import { NgComponentOutlet } from '@angular/common';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { Dialog } from '../../componentes/dialog/dialog';
import { LayoutHome } from '../../servicos/layout-home/layout-home';
import { Sessao } from '../../servicos/sessao/sessao';
import { UsoIa } from '../../servicos/uso-ia/uso-ia';
import { CATALOGO_WIDGETS_HOME, DefinicaoWidgetHome, ItemLayoutHome, definicaoWidgetHome } from './catalogo-widgets-home';

// Consumo de IA muda sozinho (poller de chamados a cada 5 min, chamadas
// reais do dia a dia) — sem isso, quem deixa a aba aberta só vê o número
// congelado do momento em que entrou, precisando dar F5 pra atualizar.
const INTERVALO_ATUALIZACAO_USO_IA_MS = 30_000;

/** Home ÚNICA — substitui `HomeRoteador` (que escolhia uma Home por módulo)
 * por uma tela só, igual pra todo mundo: hero genérico + UMA grade de
 * widgets personalizável (2026-09), começando em BRANCO.
 *
 * Diferente da primeira versão desta tela, os antigos "atalhos" fixos
 * (Central de suporte, Segurança de TI, Análise de Candidato...) NÃO são
 * mais uma seção separada e sempre visível — viraram widget igual
 * qualquer indicador de dado, com o mesmo mecanismo de
 * adicionar/remover/reordenar/redimensionar (ver `WidgetAtalho`,
 * `componentes/widget-atalho/`, e o catálogo em `catalogo-widgets-home.ts`).
 * A ÚNICA diferença entre os dois tipos de widget é o componente por trás
 * do id: um busca o próprio dado (`widget-chamados-total` e companhia), o
 * outro só recebe conteúdo estático pronto via `props`
 * (`NgComponentOutletInputs`) — pra esta tela os dois são a mesma coisa.
 *
 * Cada widget é resolvido a partir de `CATALOGO_WIDGETS_HOME` — esta tela
 * só sabe QUAIS ids mostrar, EM QUE ORDEM e EM QUE TAMANHO (`LayoutHome`,
 * persistido no backend por usuário), não como cada um funciona por
 * dentro, e renderiza cada um via `NgComponentOutlet` (em vez de um
 * `@switch` fixo) — widget novo só precisa somar uma entrada no catálogo,
 * nada muda aqui. O catálogo DISPONÍVEL pra adicionar é filtrado pelos
 * módulos liberados do usuário (`sessao.modulos()`): financeiro só vê
 * widget de financeiro, TI só vê o de TI, quem tem os dois papéis vê os
 * dois catálogos juntos — widget SEM módulo dono (`modulo: null`, ex:
 * "Central de suporte") aparece pra qualquer um, sem esse filtro. Widgets
 * que exigem `sessao.ehDesenvolvedor()` (hoje só os de IA do TI) ou
 * `sessao.administrador()` (hoje só "Usuários") somam mais esse filtro por
 * cima — o polling de `UsoIa` continua orquestrado aqui (não em cada
 * widget), senão vários widgets de IA abertos ao mesmo tempo disparariam
 * requests redundantes. */
@Component({
  selector: 'app-home',
  imports: [CdkDrag, CdkDragHandle, CdkDropList, Dialog, NgComponentOutlet],
  templateUrl: './home.html',
  styleUrl: './home.scss',
})
export class Home {
  protected readonly sessao = inject(Sessao);
  protected readonly usoIa = inject(UsoIa);
  protected readonly layoutHome = inject(LayoutHome);

  protected readonly modoEdicao = signal(false);
  protected readonly catalogoAberto = signal(false);

  private readonly acessoLiberado = (definicao: DefinicaoWidgetHome): boolean =>
    (definicao.modulo === null || this.sessao.modulos().includes(definicao.modulo)) &&
    (!definicao.disponibilidadeDev || this.sessao.ehDesenvolvedor()) &&
    (!definicao.exigeAdministrador || this.sessao.administrador());

  // Defesa em profundidade: o backend já filtra id desconhecido, id sem
  // acesso ao módulo, id que exige desenvolvedor/administrador e tamanho
  // inválido antes de devolver o layout
  // (`server/home/dashboard.py::_layout_visivel`), mas essa tela não
  // confia só nisso — um layout salvo/cacheado de outra sessão (ex:
  // alguém que perdeu um papel) nunca deveria renderizar um widget sem
  // acesso aqui.
  protected readonly widgetsVisiveis = computed<ItemLayoutHome[]>(() =>
    this.layoutHome.widgets().filter((item) => {
      const definicao = definicaoWidgetHome(item.id);
      return definicao !== undefined && this.acessoLiberado(definicao);
    }),
  );

  protected readonly catalogoDisponivel = computed(() => {
    const jaVisiveis = new Set(this.widgetsVisiveis().map((item) => item.id));
    return CATALOGO_WIDGETS_HOME.filter(
      (definicao) => this.acessoLiberado(definicao) && !jaVisiveis.has(definicao.id),
    );
  });

  constructor() {
    this.layoutHome.carregar();
    if (this.sessao.ehDesenvolvedor()) {
      this.usoIa.carregar();
      const intervalo = setInterval(() => this.usoIa.carregar(), INTERVALO_ATUALIZACAO_USO_IA_MS);
      inject(DestroyRef).onDestroy(() => clearInterval(intervalo));
    }
  }

  protected componenteDoWidget(id: string) {
    return definicaoWidgetHome(id)?.componente ?? null;
  }

  /** `NgComponentOutletInputs` do widget — indicador de dado não recebe
   * nada (`{}`, busca o próprio dado sozinho); widget de atalho recebe o
   * conteúdo estático do catálogo (`props`). Tipado como `Record<string,
   * unknown>` (o que `NgComponentOutletInputs` exige), não como
   * `PropsWidgetAtalho` — quem lê essas props de volta com tipo é o
   * próprio `WidgetAtalho`, via `input.required<string>()` etc. */
  protected propsDoWidget(id: string): Record<string, unknown> {
    return { ...(definicaoWidgetHome(id)?.props ?? {}) };
  }

  protected onSoltar(evento: CdkDragDrop<ItemLayoutHome[]>): void {
    const widgets = [...this.widgetsVisiveis()];
    moveItemInArray(widgets, evento.previousIndex, evento.currentIndex);
    this.layoutHome.agendarSalvar(widgets);
  }

  // Diálogo fica aberto depois de adicionar de propósito — permite
  // escolher vários widgets em sequência sem reabrir o diálogo a cada um
  // (fecha só quando o usuário clica em Fechar/Esc/fora).
  protected adicionarWidget(id: string): void {
    const definicao = definicaoWidgetHome(id);
    if (!definicao) {
      return;
    }
    this.layoutHome.salvarAgora([...this.widgetsVisiveis(), { id, tamanho: definicao.tamanhoPadrao }]);
  }

  protected removerWidget(id: string): void {
    this.layoutHome.salvarAgora(this.widgetsVisiveis().filter((item) => item.id !== id));
  }

  protected alternarTamanho(id: string): void {
    const widgets = this.widgetsVisiveis().map((item) =>
      item.id === id ? { ...item, tamanho: item.tamanho === 'grande' ? ('pequeno' as const) : ('grande' as const) } : item,
    );
    this.layoutHome.salvarAgora(widgets);
  }
}
