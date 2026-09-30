import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { vi } from 'vitest';
import { LayoutHome } from '../../servicos/layout-home/layout-home';
import { Sessao } from '../../servicos/sessao/sessao';
import { TetoTokensIa } from '../../servicos/teto-tokens-ia/teto-tokens-ia';
import { ChamadosIaResposta, UsoIa } from '../../servicos/uso-ia/uso-ia';
import { ItemLayoutHome } from './catalogo-widgets-home';
import { Home } from './home';

function item(id: string, tamanho: ItemLayoutHome['tamanho'] = 'pequeno'): ItemLayoutHome {
  return { id, tamanho };
}

function sessaoFalso(
  modulos: string[] = ['ti'],
  ehDesenvolvedor = false,
  administrador = false,
  ehAdminDoModulo: (modulo: string) => boolean = () => false,
) {
  return {
    modulos: () => modulos,
    ehDesenvolvedor: () => ehDesenvolvedor,
    administrador: () => administrador,
    ehAdminDoModulo,
    nome: () => 'Daniel',
  };
}

function tetoTokensIaFalso() {
  return {
    teto: signal<number | null>(0),
    tokensHoje: signal(0),
    carregar: vi.fn(),
    salvar: vi.fn(() => of({ dominio: 'rh', teto_tokens_diario: 7000, tokens_hoje: 0 })),
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
  tetoTokensIa = tetoTokensIaFalso(),
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
      { provide: TetoTokensIa, useValue: tetoTokensIa },
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
    tetoTokensIa,
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
    botaoConfigIa: () => el.querySelector('.botao-config-ia') as HTMLButtonElement | null,
    abrirConfiguracoesIa: () => {
      (el.querySelector('.botao-config-ia') as HTMLButtonElement).click();
      fixture.detectChanges();
    },
    ativarTetoIa: () => {
      (el.querySelector('.interruptor') as HTMLButtonElement).click();
      fixture.detectChanges();
    },
    digitarTetoIa: (valorTexto: string) => {
      const campo = el.querySelector('app-campo-numerico input') as HTMLInputElement;
      campo.value = valorTexto;
      campo.dispatchEvent(new Event('input'));
      fixture.detectChanges();
    },
    botaoSalvarTetoIa: () =>
      Array.from(el.querySelectorAll('.botoes-rodape button')).find((b) =>
        b.textContent?.includes('Salvar teto'),
      ) as HTMLButtonElement,
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

    it('em modo de edição, o conteúdo do widget fica num wrapper próprio (`.corpo-widget`), separado da barra de edição', () => {
      // Regressão: sem esse wrapper, o conteúdo do widget (que declara
      // `height: 100%` no próprio `:host`) resolvia contra a altura toda
      // do `.widget-arrastavel` — sem descontar o espaço da barra de
      // edição acima dele — e vazava por baixo, sobrepondo a linha
      // seguinte da grade (e confundindo o cálculo de posição do CDK ao
      // arrastar). Ver comentário de `.widget-arrastavel`/`.corpo-widget`
      // em `home.scss`.
      const { fixture, ligarPersonalizar } = criar();

      ligarPersonalizar();

      const widget = fixture.nativeElement.querySelector('.widget-arrastavel') as HTMLElement;
      const barra = widget.querySelector(':scope > .barra-edicao-widget');
      const corpo = widget.querySelector(':scope > .corpo-widget');
      expect(corpo).not.toBeNull();
      expect(corpo?.children.length).toBeGreaterThan(0);
      expect(barra?.compareDocumentPosition(corpo!)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
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

  describe('engrenagem de teto de tokens de IA (admin de módulo sem tela própria)', () => {
    it('não aparece pra quem não administra nenhum dos módulos configuráveis', () => {
      const { botaoConfigIa } = criar(sessaoFalso(['rh'], false, false));

      expect(botaoConfigIa()).toBeNull();
    });

    it('não aparece pro admin do TI (já tem tela própria em /ti/provedores)', () => {
      const { botaoConfigIa } = criar(sessaoFalso(['ti'], false, true, (modulo) => modulo === 'ti'));

      expect(botaoConfigIa()).toBeNull();
    });

    it('aparece pro admin do RH e carrega o teto/consumo do domínio "rh"', () => {
      const tetoTokensIa = tetoTokensIaFalso();
      const { botaoConfigIa } = criar(
        sessaoFalso(['rh'], false, true, (modulo) => modulo === 'rh'),
        usoIaFalso(),
        undefined,
        tetoTokensIa,
      );

      expect(botaoConfigIa()).not.toBeNull();
      expect(tetoTokensIa.carregar).toHaveBeenCalledWith('rh');
    });

    it('com teto desativado (0, padrão do fake), o campo do valor começa desabilitado', () => {
      const { abrirConfiguracoesIa, fixture } = criar(
        sessaoFalso(['rh'], false, true, (modulo) => modulo === 'rh'),
      );
      abrirConfiguracoesIa();

      const campo = fixture.nativeElement.querySelector('app-campo-numerico input') as HTMLInputElement;
      expect(campo.disabled).toBe(true);
    });

    it('ativar o interruptor habilita o campo pro admin digitar o teto', () => {
      const { abrirConfiguracoesIa, ativarTetoIa, fixture } = criar(
        sessaoFalso(['rh'], false, true, (modulo) => modulo === 'rh'),
      );
      abrirConfiguracoesIa();
      const campo = fixture.nativeElement.querySelector('app-campo-numerico input') as HTMLInputElement;
      expect(campo.disabled).toBe(true);

      ativarTetoIa();

      expect(campo.disabled).toBe(false);
    });

    it('salvar com o teto desativado sempre manda 0, mesmo com número digitado antes de desativar', () => {
      const tetoTokensIa = tetoTokensIaFalso();
      const { abrirConfiguracoesIa, ativarTetoIa, digitarTetoIa, botaoSalvarTetoIa, fixture } = criar(
        sessaoFalso(['rh'], false, true, (modulo) => modulo === 'rh'),
        usoIaFalso(),
        undefined,
        tetoTokensIa,
      );

      abrirConfiguracoesIa();
      ativarTetoIa();
      digitarTetoIa('7000');
      ativarTetoIa(); // desativa de novo

      botaoSalvarTetoIa().click();
      fixture.detectChanges();

      expect(tetoTokensIa.salvar).toHaveBeenCalledWith('rh', 0);
    });

    it('salvar teto válido chama o serviço com o domínio "rh" e fecha o diálogo', () => {
      const tetoTokensIa = tetoTokensIaFalso();
      const { abrirConfiguracoesIa, ativarTetoIa, digitarTetoIa, botaoSalvarTetoIa, texto, fixture } = criar(
        sessaoFalso(['rh'], false, true, (modulo) => modulo === 'rh'),
        usoIaFalso(),
        undefined,
        tetoTokensIa,
      );

      abrirConfiguracoesIa();
      ativarTetoIa();
      digitarTetoIa('7000');
      botaoSalvarTetoIa().click();
      fixture.detectChanges();

      expect(tetoTokensIa.salvar).toHaveBeenCalledWith('rh', 7000);
      expect(texto()).not.toContain('Salvar teto');
    });
  });
});
