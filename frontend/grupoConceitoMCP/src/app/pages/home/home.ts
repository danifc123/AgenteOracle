import { CdkDrag, CdkDragDrop, CdkDragHandle, CdkDropList, moveItemInArray } from '@angular/cdk/drag-drop';
import { NgComponentOutlet } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, computed, effect, inject, signal } from '@angular/core';
import { CampoNumerico } from '../../componentes/campo-numerico/campo-numerico';
import { Dialog } from '../../componentes/dialog/dialog';
import { Interruptor } from '../../componentes/interruptor/interruptor';
import { Selo } from '../../componentes/selo/selo';
import { LayoutHome } from '../../servicos/layout-home/layout-home';
import { mensagemErro } from '../../servicos/mensagens-erro/mensagens-erro';
import { Sessao } from '../../servicos/sessao/sessao';
import { TetoTokensIa } from '../../servicos/teto-tokens-ia/teto-tokens-ia';
import { UsoIa } from '../../servicos/uso-ia/uso-ia';
import { CATALOGO_WIDGETS_HOME, DefinicaoWidgetHome, ItemLayoutHome, definicaoWidgetHome } from './catalogo-widgets-home';

// Departamentos que ainda não têm uma tela própria de administração de IA
// (diferente do TI, que já tem `/ti/provedores`) — o admin desses módulos
// configura o teto de tokens por uma engrenagem aqui na Home mesmo,
// enquanto não existir uma tela dedicada (ver plano de
// 2026-09-29: "teto diário de tokens por departamento"). Somar um módulo
// aqui é o único passo pra ele ganhar a mesma engrenagem.
const DOMINIOS_COM_ENGRENAGEM_NA_HOME = ['rh'] as const;

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
  imports: [CampoNumerico, CdkDrag, CdkDragHandle, CdkDropList, Dialog, Interruptor, NgComponentOutlet, Selo],
  templateUrl: './home.html',
  styleUrl: './home.scss',
})
export class Home {
  protected readonly sessao = inject(Sessao);
  protected readonly usoIa = inject(UsoIa);
  protected readonly layoutHome = inject(LayoutHome);
  protected readonly tetoTokensIa = inject(TetoTokensIa);

  protected readonly modoEdicao = signal(false);
  protected readonly catalogoAberto = signal(false);

  /** Primeiro (e único, por enquanto) domínio de `DOMINIOS_COM_ENGRENAGEM_
   * NA_HOME` que o usuário logado administra — `null` esconde a
   * engrenagem inteira. Sem tela própria de administração ainda (ver
   * constante acima), então só suporta o usuário ser admin de UM desses
   * domínios de cada vez; suficiente pro escopo atual (só RH). */
  protected readonly dominioConfiguravel = computed<string | null>(
    () => DOMINIOS_COM_ENGRENAGEM_NA_HOME.find((dominio) => this.sessao.ehAdminDoModulo(dominio)) ?? null,
  );

  protected readonly configuracoesIaAbertas = signal(false);
  protected readonly tetoIaAtivo = signal(false);
  protected readonly tetoIaTexto = signal('0');
  protected readonly salvandoTetoIa = signal(false);
  protected readonly erroTetoIa = signal<string | null>(null);

  protected readonly tetoIaValido = computed<number | null>(() => {
    // Desativado = sempre salva "sem teto" (0) — mesma regra de
    // `pages/modulos/ti/provedores/provedores.ts::tetoValido`.
    if (!this.tetoIaAtivo()) {
      return 0;
    }
    const numero = Number(this.tetoIaTexto());
    return Number.isInteger(numero) && numero > 0 ? numero : null;
  });

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

    const dominio = this.dominioConfiguravel();
    if (dominio) {
      this.tetoTokensIa.carregar(dominio);
      // Semeia o rascunho do teto sempre que o valor real do servidor muda
      // (primeiro load, e depois de salvar) — mesmo espírito do dialog de
      // teto em `pages/modulos/ti/provedores/provedores.ts`.
      effect(() => {
        const teto = this.tetoTokensIa.teto();
        if (teto !== null) {
          this.tetoIaTexto.set(String(teto));
          this.tetoIaAtivo.set(teto > 0);
        }
      });
    }
  }

  protected salvarTetoIa(): void {
    const dominio = this.dominioConfiguravel();
    const teto = this.tetoIaValido();
    if (!dominio || teto === null || this.salvandoTetoIa()) {
      return;
    }

    this.salvandoTetoIa.set(true);
    this.erroTetoIa.set(null);
    this.tetoTokensIa.salvar(dominio, teto).subscribe({
      next: () => {
        this.salvandoTetoIa.set(false);
        this.configuracoesIaAbertas.set(false);
      },
      error: (erro: HttpErrorResponse) => {
        this.erroTetoIa.set(mensagemErro(erro, 'Não foi possível salvar o teto de tokens.'));
        this.salvandoTetoIa.set(false);
      },
    });
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
