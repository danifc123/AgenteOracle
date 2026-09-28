import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { vi } from 'vitest';
import { LayoutHome } from '../../servicos/layout-home/layout-home';
import { Sessao } from '../../servicos/sessao/sessao';
import { ChamadosIaResposta, UsoIa } from '../../servicos/uso-ia/uso-ia';
import { ItemLayoutHome } from './catalogo-widgets-home';
import { Home } from './home';

function item(id: string, tamanho: ItemLayoutHome['tamanho'] = 'pequeno'): ItemLayoutHome {
  return { id, tamanho };
}

function sessaoFalso(modulos: string[] = ['ti'], ehDesenvolvedor = false, administrador = false) {
  return {
    modulos: () => modulos,
    ehDesenvolvedor: () => ehDesenvolvedor,
    administrador: () => administrador,
    nome: () => 'Daniel',
  };
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

function layoutHomeFalso(widgets: ItemLayoutHome[] = []) {
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
  layoutHome = layoutHomeFalso([item('ti:chamados_total'), item('ti:chamados_por_status', 'grande')]),
) {
  TestBed.configureTestingModule({
    imports: [Home],
    providers: [
      provideRouter([]),
      provideHttpClient(),
      provideHttpClientTesting(),
      { provide: Sessao, useValue: sessao },
      { provide: UsoIa, useValue: usoIa },
      { provide: LayoutHome, useValue: layoutHome },
    ],
  });
  const fixture = TestBed.createComponent(Home);
  const http = TestBed.inject(HttpTestingController);
  fixture.detectChanges();

  const el: HTMLElement = fixture.nativeElement;
  return {
    fixture,
    usoIa,
    layoutHome,
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

describe('Home', () => {
  afterEach(() => {
    // Widgets de chamados/segurança/financeiro fazem seu próprio GET — libera
    // sem asserir corpo (cada widget tem seu spec próprio pra isso), só
    // evita requests presas.
    TestBed.inject(HttpTestingController)
      .match(() => true)
      .forEach((req) => req.flush([]));
  });

  it('carrega o layout salvo ao entrar na tela', () => {
    const layoutHome = layoutHomeFalso();

    criar(sessaoFalso(), usoIaFalso(), layoutHome);

    expect(layoutHome.carregar).toHaveBeenCalled();
  });

  it('sem nenhum widget escolhido, mostra a mensagem de personalizar', () => {
    const { texto } = criar(sessaoFalso(), usoIaFalso(), layoutHomeFalso([]));

    expect(texto()).toContain('Nenhum widget escolhido');
  });

  describe('aviso da Área de Trabalho', () => {
    it('não aparece pra quem não tem o módulo financeiro', () => {
      const { texto } = criar(sessaoFalso(['ti']));

      expect(texto()).not.toContain('Área de Trabalho');
    });

    it('aparece pra quem tem o módulo financeiro', () => {
      const { texto } = criar(sessaoFalso(['financeiro']));

      expect(texto()).toContain('Área de Trabalho');
    });
  });

  describe('widgets filtrados por módulo liberado (indicador de dado OU atalho, mesmo filtro)', () => {
    it('usuário só-financeiro não vê widget de TI mesmo que o layout salvo contenha um', () => {
      const { fixture } = criar(
        sessaoFalso(['financeiro']),
        usoIaFalso(),
        layoutHomeFalso([item('financeiro:saldo_projetado'), item('ti:chamados_total'), item('ti:seguranca')]),
      );

      expect(fixture.nativeElement.querySelector('app-widget-saldo-projetado')).not.toBeNull();
      expect(fixture.nativeElement.querySelector('app-widget-chamados-total')).toBeNull();
      expect(fixture.nativeElement.textContent).not.toContain('Segurança de TI');
    });

    it('usuário só-TI não vê widget de financeiro mesmo que o layout salvo contenha um', () => {
      const { fixture } = criar(
        sessaoFalso(['ti']),
        usoIaFalso(),
        layoutHomeFalso([item('financeiro:saldo_projetado'), item('ti:chamados_total'), item('financeiro:criar_relatorio')]),
      );

      expect(fixture.nativeElement.querySelector('app-widget-saldo-projetado')).toBeNull();
      expect(fixture.nativeElement.querySelector('app-widget-chamados-total')).not.toBeNull();
      expect(fixture.nativeElement.textContent).not.toContain('Criar relatório');
    });

    it('usuário com os dois módulos vê os widgets dos dois catálogos juntos', () => {
      const { fixture } = criar(
        sessaoFalso(['financeiro', 'ti']),
        usoIaFalso(),
        layoutHomeFalso([item('financeiro:saldo_projetado'), item('ti:chamados_total')]),
      );

      expect(fixture.nativeElement.querySelector('app-widget-saldo-projetado')).not.toBeNull();
      expect(fixture.nativeElement.querySelector('app-widget-chamados-total')).not.toBeNull();
    });

    it('widget marcado como "grande" recebe a classe de 2 colunas', () => {
      const { fixture } = criar(
        sessaoFalso(['ti']),
        usoIaFalso(),
        layoutHomeFalso([item('ti:chamados_total', 'pequeno'), item('ti:chamados_por_status', 'grande')]),
      );

      const widgets = Array.from(fixture.nativeElement.querySelectorAll('.widget-arrastavel')) as HTMLElement[];
      expect(widgets[0].classList.contains('widget-grande')).toBe(false);
      expect(widgets[1].classList.contains('widget-grande')).toBe(true);
    });

    it('usuário que não é desenvolvedor não vê indicador de IA, mesmo se o layout salvo contiver um', () => {
      const { fixture } = criar(
        sessaoFalso(['ti'], false),
        usoIaFalso(),
        layoutHomeFalso([item('ti:chamados_total'), item('ti:ia_tokens_hoje')]),
      );

      expect(fixture.nativeElement.querySelector('app-widget-ia-tokens-hoje')).toBeNull();
    });

    it('desenvolvedor vê indicador de IA quando está no layout', () => {
      const { fixture } = criar(
        sessaoFalso(['ti'], true),
        usoIaFalso(),
        layoutHomeFalso([item('ti:ia_tokens_hoje')]),
      );

      expect(fixture.nativeElement.querySelector('app-widget-ia-tokens-hoje')).not.toBeNull();
    });
  });

  describe('widgets comuns (sem módulo dono)', () => {
    it('renderiza o widget de atalho com o conteúdo do catálogo (título, texto e link)', () => {
      const { fixture } = criar(sessaoFalso(['ti']), usoIaFalso(), layoutHomeFalso([item('comum:central_suporte')]));

      const texto = fixture.nativeElement.textContent as string;
      expect(texto).toContain('Central de suporte');
      const link: HTMLAnchorElement | null = fixture.nativeElement.querySelector('app-widget-atalho a');
      expect(link?.getAttribute('href')).toBe('https://suporte.grupoconceito.com/front/central.php');
    });

    it('"Central de suporte" aparece pra qualquer papel, mesmo sem nenhum módulo em comum com o dono', () => {
      const { fixture } = criar(sessaoFalso(['rh']), usoIaFalso(), layoutHomeFalso([item('comum:central_suporte')]));

      expect(fixture.nativeElement.querySelector('app-widget-atalho')).not.toBeNull();
    });

    it('"Usuários" some do layout salvo pra quem não é administrador', () => {
      const { fixture } = criar(
        sessaoFalso(['financeiro'], false, false),
        usoIaFalso(),
        layoutHomeFalso([item('comum:usuarios')]),
      );

      expect(fixture.nativeElement.querySelector('app-widget-atalho')).toBeNull();
    });

    it('"Usuários" aparece no layout salvo pra qualquer administrador', () => {
      const { fixture } = criar(
        sessaoFalso(['financeiro'], false, true),
        usoIaFalso(),
        layoutHomeFalso([item('comum:usuarios')]),
      );

      expect(fixture.nativeElement.querySelector('app-widget-atalho')).not.toBeNull();
    });
  });

  describe('polling de consumo de IA', () => {
    it('usuário comum não dispara o polling', () => {
      const usoIa = usoIaFalso();

      criar(sessaoFalso(['ti'], false), usoIa);

      expect(usoIa.carregar).not.toHaveBeenCalled();
    });

    it('desenvolvedor: consumo de IA atualiza sozinho, sem precisar de F5', () => {
      vi.useFakeTimers();
      const usoIa = usoIaFalso();
      criar(sessaoFalso(['ti'], true), usoIa);

      expect(usoIa.carregar).toHaveBeenCalledTimes(1); // carga inicial, ao entrar na tela

      vi.advanceTimersByTime(30_000);
      expect(usoIa.carregar).toHaveBeenCalledTimes(2);

      vi.useRealTimers();
    });
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

    it('catálogo só mostra widgets (indicador ou atalho) do módulo liberado pro usuário', () => {
      const { texto, ligarPersonalizar, abrirCatalogo } = criar(sessaoFalso(['financeiro']));

      ligarPersonalizar();
      abrirCatalogo();

      expect(texto()).toContain('Saldo projetado');
      expect(texto()).toContain('Faturamento total');
      expect(texto()).toContain('Criar relatório');
      expect(texto()).not.toContain('Chamados em aberto');
      expect(texto()).not.toContain('Segurança de TI');
    });

    it('catálogo mostra o atalho de TI mesmo pra quem não é desenvolvedor (atalho não exige dev)', () => {
      const { texto, ligarPersonalizar, abrirCatalogo } = criar(sessaoFalso(['ti'], false));

      ligarPersonalizar();
      abrirCatalogo();

      expect(texto()).toContain('Segurança de TI');
      expect(texto()).toContain('Auditoria de Chamados');
    });

    it('catálogo exclui indicador de IA e inclui achados de segurança pra quem não é desenvolvedor', () => {
      const { texto, ligarPersonalizar, abrirCatalogo } = criar(sessaoFalso(['ti'], false));

      ligarPersonalizar();
      abrirCatalogo();

      expect(texto()).toContain('Chamados em aberto');
      expect(texto()).toContain('Achados de segurança ativos');
      expect(texto()).not.toContain('Tokens hoje');
    });

    it('catálogo sempre mostra "Central de suporte", qualquer que seja o papel', () => {
      const { texto, ligarPersonalizar, abrirCatalogo } = criar(sessaoFalso(['rh']));

      ligarPersonalizar();
      abrirCatalogo();

      expect(texto()).toContain('Central de suporte');
    });

    it('catálogo só mostra "Usuários" pra administrador', () => {
      const semAdmin = criar(sessaoFalso(['financeiro'], false, false));
      semAdmin.ligarPersonalizar();
      semAdmin.abrirCatalogo();
      expect(semAdmin.texto()).not.toContain('Usuários');
    });

    it('catálogo mostra "Usuários" pra qualquer administrador de módulo', () => {
      const comAdmin = criar(sessaoFalso(['financeiro'], false, true));
      comAdmin.ligarPersonalizar();
      comAdmin.abrirCatalogo();
      expect(comAdmin.texto()).toContain('Usuários');
    });

    it('catálogo exclui widget já presente no layout atual', () => {
      const { texto, ligarPersonalizar, abrirCatalogo } = criar(
        sessaoFalso(['ti']),
        usoIaFalso(),
        layoutHomeFalso([item('ti:chamados_total')]),
      );

      ligarPersonalizar();
      abrirCatalogo();

      expect(texto()).not.toContain('+ Chamados em aberto');
      expect(texto()).toContain('+ Chamados por status');
    });

    it('clicar num item do catálogo chama salvarAgora com o tamanho padrão dele (sem debounce)', () => {
      const layoutHome = layoutHomeFalso([]);
      const { fixture, ligarPersonalizar, abrirCatalogo } = criar(sessaoFalso(['ti']), usoIaFalso(), layoutHome);

      ligarPersonalizar();
      abrirCatalogo();
      (fixture.nativeElement.querySelector('.botao-opcao-catalogo') as HTMLButtonElement).click();

      expect(layoutHome.salvarAgora).toHaveBeenCalledWith([item('ti:chamados_total', 'pequeno')]);
    });

    it('clicar em remover widget chama salvarAgora (sem debounce)', () => {
      const layoutHome = layoutHomeFalso([item('ti:chamados_total'), item('ti:chamados_por_status')]);
      const { fixture, ligarPersonalizar } = criar(sessaoFalso(['ti']), usoIaFalso(), layoutHome);

      ligarPersonalizar();
      (fixture.nativeElement.querySelector('.botao-remover-widget') as HTMLButtonElement).click();

      expect(layoutHome.salvarAgora).toHaveBeenCalledWith([item('ti:chamados_por_status')]);
    });

    it('clicar em alternar tamanho troca pequeno/grande e chama salvarAgora (sem debounce)', () => {
      const layoutHome = layoutHomeFalso([item('ti:chamados_total', 'pequeno')]);
      const { fixture, ligarPersonalizar } = criar(sessaoFalso(['ti']), usoIaFalso(), layoutHome);

      ligarPersonalizar();
      (fixture.nativeElement.querySelector('.botao-alternar-tamanho') as HTMLButtonElement).click();

      expect(layoutHome.salvarAgora).toHaveBeenCalledWith([item('ti:chamados_total', 'grande')]);
    });

    it('soltar um item arrastado chama agendarSalvar (com debounce) com a ordem nova', () => {
      const layoutHome = layoutHomeFalso([item('ti:chamados_total'), item('ti:chamados_por_status')]);
      const { fixture } = criar(sessaoFalso(['ti']), usoIaFalso(), layoutHome);

      // Simula o evento que o `(cdkDropListDropped)` do template passaria —
      // só os dois campos que `onSoltar` de fato lê.
      (fixture.componentInstance as unknown as { onSoltar(evento: unknown): void }).onSoltar({
        previousIndex: 0,
        currentIndex: 1,
      });

      expect(layoutHome.agendarSalvar).toHaveBeenCalledWith([item('ti:chamados_por_status'), item('ti:chamados_total')]);
    });
  });
});
