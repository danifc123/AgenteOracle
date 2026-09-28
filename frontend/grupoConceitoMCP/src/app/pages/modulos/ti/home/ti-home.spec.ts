import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { vi } from 'vitest';
import { LayoutDashboardTi } from '../../../../servicos/layout-dashboard-ti/layout-dashboard-ti';
import { Sessao } from '../../../../servicos/sessao/sessao';
import { ChamadosIaResposta, UsoIa } from '../../../../servicos/uso-ia/uso-ia';
import { ItemLayoutTi } from './widgets/catalogo-widgets-ti';
import { TiHome } from './ti-home';

function item(id: ItemLayoutTi['id'], tamanho: ItemLayoutTi['tamanho'] = 'pequeno'): ItemLayoutTi {
  return { id, tamanho };
}

function sessaoFalso(ehDesenvolvedor = false) {
  return { ehDesenvolvedor: () => ehDesenvolvedor };
}

function usoIaFalso() {
  return {
    tokensHojePorDominio: signal<Record<string, number>>({ ti: 300, rh: 200 }),
    chamadosIa: signal<ChamadosIaResposta | null>({
      total_chamados: 10,
      avaliados_insuficientes: 2,
      com_fallback_embedding: 1,
      duracao_media_ms: 500,
    }),
    carregar: vi.fn(),
  };
}

function layoutDashboardFalso(widgets: ItemLayoutTi[] = []) {
  return {
    widgets: signal(widgets),
    carregar: vi.fn(),
    agendarSalvar: vi.fn(),
    salvarAgora: vi.fn(),
  };
}

function criar(
  sessao = sessaoFalso(),
  usoIa = usoIaFalso(),
  layoutDashboard = layoutDashboardFalso([item('chamados_total'), item('chamados_por_status', 'grande')]),
) {
  TestBed.configureTestingModule({
    imports: [TiHome],
    providers: [
      provideRouter([]),
      provideHttpClient(),
      provideHttpClientTesting(),
      { provide: Sessao, useValue: sessao },
      { provide: UsoIa, useValue: usoIa },
      { provide: LayoutDashboardTi, useValue: layoutDashboard },
    ],
  });
  const fixture = TestBed.createComponent(TiHome);
  const http = TestBed.inject(HttpTestingController);
  fixture.detectChanges();

  const el: HTMLElement = fixture.nativeElement;
  return {
    fixture,
    usoIa,
    layoutDashboard,
    http,
    texto: () => el.textContent ?? '',
    ligarPersonalizar: () => {
      (el.querySelector('.botao-personalizar') as HTMLButtonElement).click();
      fixture.detectChanges();
    },
    abrirCatalogo: () => {
      (el.querySelector('.botao-adicionar') as HTMLButtonElement).click();
      fixture.detectChanges();
    },
  };
}

describe('TiHome', () => {
  afterEach(() => {
    // Widgets de chamados/segurança fazem seu próprio GET — libera sem
    // asserir corpo (cada widget tem seu spec próprio pra isso), só evita
    // requests presas.
    TestBed.inject(HttpTestingController)
      .match(() => true)
      .forEach((req) => req.flush([]));
  });

  it('atalhos de sempre continuam presentes (Segurança, Auditoria de Chamados, Central de suporte)', () => {
    const { texto } = criar();

    expect(texto()).toContain('Segurança de TI');
    expect(texto()).toContain('Auditoria de Chamados');
    expect(texto()).toContain('Central de suporte');
  });

  it('carrega o layout salvo ao entrar na tela', () => {
    const layoutDashboard = layoutDashboardFalso();

    criar(sessaoFalso(), usoIaFalso(), layoutDashboard);

    expect(layoutDashboard.carregar).toHaveBeenCalled();
  });

  it('sem nenhum indicador escolhido, mostra a mensagem de personalizar', () => {
    const { texto } = criar(sessaoFalso(), usoIaFalso(), layoutDashboardFalso([]));

    expect(texto()).toContain('Nenhum indicador escolhido');
  });

  it('renderiza o widget de cada item do layout, na ordem', () => {
    const { fixture } = criar(
      sessaoFalso(),
      usoIaFalso(),
      layoutDashboardFalso([item('chamados_por_status'), item('chamados_total')]),
    );

    const elementos: NodeListOf<Element> = fixture.nativeElement.querySelectorAll(
      '.widget-arrastavel > *:last-child',
    );
    const ids = Array.from(elementos).map((el) => el.tagName.toLowerCase());
    expect(ids).toEqual(['app-widget-chamados-por-status', 'app-widget-chamados-total']);
  });

  it('widget marcado como "grande" recebe a classe de 2 colunas', () => {
    const { fixture } = criar(
      sessaoFalso(),
      usoIaFalso(),
      layoutDashboardFalso([item('chamados_total', 'pequeno'), item('chamados_por_status', 'grande')]),
    );

    const widgets = Array.from(fixture.nativeElement.querySelectorAll('.widget-arrastavel')) as HTMLElement[];
    expect(widgets[0].classList.contains('widget-grande')).toBe(false);
    expect(widgets[1].classList.contains('widget-grande')).toBe(true);
  });

  it('usuário que não é desenvolvedor não vê indicador de IA, mesmo se o layout salvo contiver um', () => {
    const { fixture } = criar(
      sessaoFalso(false),
      usoIaFalso(),
      layoutDashboardFalso([item('chamados_total'), item('ia_tokens_hoje')]),
    );

    expect(fixture.nativeElement.querySelector('app-widget-ia-tokens-hoje')).toBeNull();
  });

  it('desenvolvedor vê indicador de IA quando está no layout', () => {
    const { fixture } = criar(sessaoFalso(true), usoIaFalso(), layoutDashboardFalso([item('ia_tokens_hoje')]));

    expect(fixture.nativeElement.querySelector('app-widget-ia-tokens-hoje')).not.toBeNull();
  });

  it('usuário de TI comum não dispara o polling de consumo de IA', () => {
    const usoIa = usoIaFalso();

    criar(sessaoFalso(false), usoIa);

    expect(usoIa.carregar).not.toHaveBeenCalled();
  });

  it('desenvolvedor: consumo de IA atualiza sozinho, sem precisar de F5', () => {
    vi.useFakeTimers();
    const usoIa = usoIaFalso();
    criar(sessaoFalso(true), usoIa);

    expect(usoIa.carregar).toHaveBeenCalledTimes(1); // carga inicial, ao entrar na tela

    vi.advanceTimersByTime(30_000);
    expect(usoIa.carregar).toHaveBeenCalledTimes(2);

    vi.advanceTimersByTime(30_000);
    expect(usoIa.carregar).toHaveBeenCalledTimes(3);

    vi.useRealTimers();
  });

  describe('personalizar', () => {
    it('começa fora do modo de edição: sem alça de arrastar nem botão de adicionar', () => {
      const { fixture } = criar();

      expect(fixture.nativeElement.querySelector('.alca-arrastar')).toBeNull();
      expect(fixture.nativeElement.querySelector('.botao-adicionar')).toBeNull();
    });

    it('clicar em Personalizar liga o modo de edição', () => {
      const { fixture, ligarPersonalizar } = criar();

      ligarPersonalizar();

      expect(fixture.nativeElement.querySelector('.alca-arrastar')).not.toBeNull();
      expect(fixture.nativeElement.querySelector('.botao-adicionar')).not.toBeNull();
    });

    it('abrir o catálogo mostra o diálogo com os indicadores disponíveis', () => {
      const { texto, ligarPersonalizar, abrirCatalogo } = criar(
        sessaoFalso(),
        usoIaFalso(),
        layoutDashboardFalso([item('chamados_total')]),
      );

      ligarPersonalizar();
      abrirCatalogo();

      expect(texto()).toContain('Chamados por status');
    });

    it('catálogo exclui indicador de IA e inclui achados de segurança pra quem não é desenvolvedor', () => {
      const { texto, ligarPersonalizar, abrirCatalogo } = criar(
        sessaoFalso(false),
        usoIaFalso(),
        layoutDashboardFalso([]),
      );

      ligarPersonalizar();
      abrirCatalogo();

      expect(texto()).toContain('Chamados em aberto');
      expect(texto()).toContain('Achados de segurança ativos');
      expect(texto()).not.toContain('Tokens hoje');
    });

    it('catálogo exclui indicador já presente no layout atual', () => {
      const { texto, ligarPersonalizar, abrirCatalogo } = criar(
        sessaoFalso(),
        usoIaFalso(),
        layoutDashboardFalso([item('chamados_total')]),
      );

      ligarPersonalizar();
      abrirCatalogo();

      expect(texto()).not.toContain('+ Chamados em aberto');
      expect(texto()).toContain('+ Chamados por status');
    });

    it('clicar num indicador do catálogo chama salvarAgora com o tamanho padrão dele (sem debounce)', () => {
      const layoutDashboard = layoutDashboardFalso([]);
      const { fixture, ligarPersonalizar, abrirCatalogo } = criar(sessaoFalso(), usoIaFalso(), layoutDashboard);

      ligarPersonalizar();
      abrirCatalogo();
      (fixture.nativeElement.querySelector('.botao-opcao-catalogo') as HTMLButtonElement).click();

      expect(layoutDashboard.salvarAgora).toHaveBeenCalledWith([item('chamados_total', 'pequeno')]);
    });

    it('clicar em remover indicador chama salvarAgora (sem debounce)', () => {
      const layoutDashboard = layoutDashboardFalso([item('chamados_total'), item('chamados_por_status')]);
      const { fixture, ligarPersonalizar } = criar(sessaoFalso(), usoIaFalso(), layoutDashboard);

      ligarPersonalizar();
      (fixture.nativeElement.querySelector('.botao-remover-widget') as HTMLButtonElement).click();

      expect(layoutDashboard.salvarAgora).toHaveBeenCalledWith([item('chamados_por_status')]);
    });

    it('clicar em alternar tamanho troca pequeno/grande e chama salvarAgora (sem debounce)', () => {
      const layoutDashboard = layoutDashboardFalso([item('chamados_total', 'pequeno')]);
      const { fixture, ligarPersonalizar } = criar(sessaoFalso(), usoIaFalso(), layoutDashboard);

      ligarPersonalizar();
      (fixture.nativeElement.querySelector('.botao-alternar-tamanho') as HTMLButtonElement).click();

      expect(layoutDashboard.salvarAgora).toHaveBeenCalledWith([item('chamados_total', 'grande')]);
    });

    it('soltar um item arrastado chama agendarSalvar (com debounce) com a ordem nova', () => {
      const layoutDashboard = layoutDashboardFalso([item('chamados_total'), item('chamados_por_status')]);
      const { fixture } = criar(sessaoFalso(), usoIaFalso(), layoutDashboard);

      // Simula o evento que o `(cdkDropListDropped)` do template passaria —
      // só os dois campos que `onSoltar` de fato lê.
      (fixture.componentInstance as unknown as { onSoltar(evento: unknown): void }).onSoltar({
        previousIndex: 0,
        currentIndex: 1,
      });

      expect(layoutDashboard.agendarSalvar).toHaveBeenCalledWith([item('chamados_por_status'), item('chamados_total')]);
    });
  });
});
