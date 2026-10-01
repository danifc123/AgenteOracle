import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { vi } from 'vitest';
import { ConfiguracoesTi } from '../../../../servicos/configuracoes-ti/configuracoes-ti';
import { Sessao } from '../../../../servicos/sessao/sessao';
import { Chamado, ChamadosTi } from './chamados';

// `tecnico_atribuido` fica `null` nestes três de propósito: na tela real ele
// só é preenchido quando o chamado vira `fila_atendimento` (status que o
// backend já filtra fora — `_precisa_atencao`) OU quando um técnico de
// verdade já pegou o chamado fora do fluxo da IA (`gerenciado_fora_do_
// sistema: true`, ver `CHAMADO_ATRIBUIDO_A_MIM`/`CHAMADO_ATRIBUIDO_A_OUTRO`
// abaixo). O filtro "Minha área" usa `area`, não `tecnico_atribuido`.
const CHAMADO_AREA_SISTEMAS: Chamado = {
  id: 1,
  titulo: 'Impressora não liga',
  descricao: 'desc',
  categoria: 'Hardware',
  status: 'novo',
  solicitante: 'joao',
  avaliacao_mensagem: null,
  criado_em: '2026-09-23T00:00:00Z',
  tecnico_atribuido: null,
  area: 'sistemas',
  gerenciado_fora_do_sistema: false,
};

const CHAMADO_AREA_INFRA: Chamado = {
  id: 2,
  titulo: 'VPN não conecta',
  descricao: 'desc',
  categoria: 'Rede',
  status: 'aguardando_usuario',
  solicitante: 'maria',
  avaliacao_mensagem: null,
  criado_em: '2026-09-23T00:00:00Z',
  tecnico_atribuido: null,
  area: 'infra',
  gerenciado_fora_do_sistema: false,
};

const CHAMADO_AREA_SISTEMAS_2: Chamado = {
  id: 3,
  titulo: 'E-mail fora do ar',
  descricao: 'desc',
  categoria: 'E-mail',
  status: 'aguardando_usuario',
  solicitante: 'pedro',
  avaliacao_mensagem: null,
  criado_em: '2026-09-23T00:00:00Z',
  tecnico_atribuido: null,
  area: 'sistemas',
  gerenciado_fora_do_sistema: false,
};

// `tecnico_atribuido: '111'` bate com o identificador de "rafa.teste" no
// roster fake abaixo — simula um chamado que esse técnico já pegou fora do
// fluxo da IA (`gerenciado_fora_do_sistema: true`, ver `tools/ti/glpi.py::
// chamado_e_alheio`). Usado pelo filtro "Meus chamados".
const CHAMADO_ATRIBUIDO_A_MIM: Chamado = {
  id: 4,
  titulo: 'Notebook não liga',
  descricao: 'desc',
  categoria: 'Hardware',
  status: 'aguardando_usuario',
  solicitante: 'ana',
  avaliacao_mensagem: null,
  criado_em: '2026-09-23T00:00:00Z',
  tecnico_atribuido: '111',
  area: 'infra',
  gerenciado_fora_do_sistema: true,
};

// Mesma ideia de `CHAMADO_ATRIBUIDO_A_MIM`, mas atribuído a OUTRO técnico
// ('222' = "outro.tecnico" no roster fake) — "Meus chamados" nunca mostra
// esse, só "Todo o departamento".
const CHAMADO_ATRIBUIDO_A_OUTRO: Chamado = {
  id: 5,
  titulo: 'Monitor piscando',
  descricao: 'desc',
  categoria: 'Hardware',
  status: 'aguardando_usuario',
  solicitante: 'carlos',
  avaliacao_mensagem: null,
  criado_em: '2026-09-23T00:00:00Z',
  tecnico_atribuido: '222',
  area: 'sistemas',
  gerenciado_fora_do_sistema: true,
};

function sessaoFalso(usuario = 'rafa.teste', ehDesenvolvedor = false) {
  return { usuario: () => usuario, ehDesenvolvedor: () => ehDesenvolvedor };
}

function configuracoesTiFalso() {
  return {
    percentualAmostragemChamados: () => 100,
    carregar: vi.fn(),
  };
}

function criar(
  sessao = sessaoFalso(),
  chamados: Chamado[] = [CHAMADO_AREA_SISTEMAS, CHAMADO_AREA_INFRA, CHAMADO_AREA_SISTEMAS_2],
) {
  TestBed.configureTestingModule({
    imports: [ChamadosTi],
    providers: [
      provideRouter([]),
      provideHttpClient(),
      provideHttpClientTesting(),
      { provide: Sessao, useValue: sessao },
      { provide: ConfiguracoesTi, useValue: configuracoesTiFalso() },
    ],
  });
  const fixture = TestBed.createComponent(ChamadosTi);
  const http = TestBed.inject(HttpTestingController);

  http.expectOne((req) => req.url.endsWith('/api/ti/chamados')).flush(chamados);
  http.expectOne((req) => req.url.endsWith('/api/ti/tecnicos')).flush([
    { identificador: '111', nome: 'Rafa Teste', usuario: 'rafa.teste', area: 'infra' },
    { identificador: '222', nome: 'Outro Técnico', usuario: 'outro.tecnico', area: 'sistemas' },
    // Área 'processos': nenhum dos 3 chamados é dessa área — testa o
    // estado vazio do FILTRO (diferente de não ter técnico vinculado
    // nenhum, que já desabilita o botão antes de chegar aqui).
    { identificador: '333', nome: 'Sem Chamado', usuario: 'sem.chamado', area: 'processos' },
  ]);
  // `app-indicadores-tecnico` (área de indicadores embutida nesta tela)
  // busca o próprio dado sozinho — sem flush aqui a request ficaria
  // pendente e `HttpTestingController.verify()` reclamaria em todo teste
  // desta tela, mesmo os que não têm nada a ver com esses indicadores.
  http.expectOne((req) => req.url.endsWith('/api/ti/chamados/meus-indicadores')).flush({
    meus_chamados: null,
    media_chamados_equipe: 0,
    meu_tempo_gasto_horas: null,
    media_tempo_gasto_equipe_horas: 0,
  });
  fixture.detectChanges();

  const el: HTMLElement = fixture.nativeElement;

  return {
    fixture,
    http,
    el,
    linhas: () => Array.from(el.querySelectorAll('table tbody tr')) as HTMLElement[],
    // `app-select-busca` (componentes/select-busca/) é um dropdown próprio,
    // não um `<select>` nativo: abre clicando `.gatilho`, cada opção é um
    // `button.opcao` com o rótulo exato de `opcoesFiltro()` — e SELECIONAR
    // uma opção fecha o painel de novo, então `opcoesDoFiltro()` só
    // enxerga alguma coisa enquanto o painel está aberto (`abrirFiltro`).
    abrirFiltro: () => {
      // `.gatilho` ALTERNA aberto/fechado — só clica se ainda não tem
      // opção visível, senão abrir-depois-de-aberto fecharia de novo.
      if (!el.querySelector('.opcao')) {
        (el.querySelector('.gatilho') as HTMLButtonElement).click();
        fixture.detectChanges();
      }
    },
    opcoesDoFiltro: () =>
      Array.from(el.querySelectorAll('.opcao')).map((opcao) => opcao.textContent?.trim()),
    selecionarFiltro: (rotulo: string) => {
      if (!el.querySelector('.opcao')) {
        (el.querySelector('.gatilho') as HTMLButtonElement).click();
        fixture.detectChanges();
      }
      const opcao = Array.from(el.querySelectorAll('.opcao')).find(
        (botao) => botao.textContent?.trim() === rotulo,
      ) as HTMLButtonElement | undefined;
      opcao?.click();
      fixture.detectChanges();
    },
  };
}

describe('ChamadosTi', () => {
  afterEach(() => {
    TestBed.inject(HttpTestingController).verify();
  });

  it('carrega e mostra todo o departamento por padrão, sem nenhum filtro selecionado', () => {
    const { linhas } = criar();

    expect(linhas().length).toBe(3);
  });

  it('o filtro sempre oferece "Todo o departamento", e "Minha área: {área}" quando a conta logada tem técnico do GLPI vinculado', () => {
    const { opcoesDoFiltro, abrirFiltro } = criar(sessaoFalso('rafa.teste'));

    abrirFiltro();

    expect(opcoesDoFiltro()).toContain('Todo o departamento');
    expect(opcoesDoFiltro()).toContain('Minha área: Infraestrutura');
  });

  it('sem técnico GLPI vinculado, a opção "Minha área" nem aparece no filtro', () => {
    const { opcoesDoFiltro, abrirFiltro } = criar(sessaoFalso('ninguem.sem.tecnico'));

    abrirFiltro();

    expect(opcoesDoFiltro()?.some((rotulo) => rotulo?.startsWith('Minha área'))).toBe(false);
  });

  it('selecionar "Minha área: ..." mostra só os chamados da área do técnico logado', () => {
    const { selecionarFiltro, linhas } = criar(sessaoFalso('rafa.teste'));

    selecionarFiltro('Minha área: Infraestrutura');

    const restantes = linhas();
    expect(restantes.length).toBe(1);
    expect(restantes[0].textContent).toContain('VPN não conecta');
  });

  it('voltar pra "Todo o departamento" depois de "Minha área" mostra a lista inteira de novo', () => {
    const { selecionarFiltro, linhas } = criar(sessaoFalso('rafa.teste'));

    selecionarFiltro('Minha área: Infraestrutura');
    selecionarFiltro('Todo o departamento');

    expect(linhas().length).toBe(3);
  });

  it('conta logada com técnico cuja área não tem nenhum chamado mostra o estado vazio do filtro, não a tabela', () => {
    const { selecionarFiltro, linhas, el } = criar(sessaoFalso('sem.chamado'));

    selecionarFiltro('Minha área: Processos');

    expect(linhas().length).toBe(0);
    expect(el.textContent).toContain('Nenhum chamado da área Processos no momento.');
  });

  it('"Meus chamados" só aparece pra conta com técnico GLPI vinculado, e mostra só o atribuído a ela', () => {
    const chamados = [CHAMADO_AREA_SISTEMAS, CHAMADO_AREA_INFRA, CHAMADO_ATRIBUIDO_A_MIM];
    const { opcoesDoFiltro, abrirFiltro, selecionarFiltro, linhas } = criar(sessaoFalso('rafa.teste'), chamados);

    abrirFiltro();
    expect(opcoesDoFiltro()).toContain('Meus chamados');

    selecionarFiltro('Meus chamados');

    const restantes = linhas();
    expect(restantes.length).toBe(1);
    expect(restantes[0].textContent).toContain('Notebook não liga');
  });

  it('"Meus chamados" não mostra chamado atribuído a OUTRO técnico', () => {
    const chamados = [CHAMADO_AREA_SISTEMAS, CHAMADO_ATRIBUIDO_A_MIM];
    // "outro.tecnico" (identificador '222') não é o técnico atribuído
    // (`CHAMADO_ATRIBUIDO_A_MIM.tecnico_atribuido === '111'`, de "rafa.teste").
    const { selecionarFiltro, linhas } = criar(sessaoFalso('outro.tecnico'), chamados);

    selecionarFiltro('Meus chamados');

    expect(linhas().length).toBe(0);
  });

  it('conta com técnico vinculado mas nenhum chamado atribuído a ela mostra o estado vazio de "Meus chamados"', () => {
    const { selecionarFiltro, linhas, el } = criar(sessaoFalso('rafa.teste'));

    selecionarFiltro('Meus chamados');

    expect(linhas().length).toBe(0);
    expect(el.textContent).toContain('Nenhum chamado atribuído a você no momento.');
  });

  it('padrão ("Todo o departamento") mostra chamado já gerenciado fora do sistema, mesmo sem nenhum filtro selecionado', () => {
    // Decisão confirmada com o usuário (2026-10-01): não existe mais um
    // "Todos" escondendo esse chamado por padrão — só "Minha área"
    // esconde (teste abaixo). O padrão mostra tudo, igual o GLPI mostraria.
    const chamados = [CHAMADO_AREA_SISTEMAS, CHAMADO_ATRIBUIDO_A_MIM, CHAMADO_ATRIBUIDO_A_OUTRO];
    const { linhas } = criar(sessaoFalso('rafa.teste'), chamados);

    expect(linhas().length).toBe(3);
  });

  it('"Minha área" também esconde chamado gerenciado fora do sistema, mesmo sendo da área certa', () => {
    // CHAMADO_ATRIBUIDO_A_MIM é área 'infra', igual a área do técnico
    // logado — ainda assim não deveria aparecer aqui (só em "Meus
    // chamados"/"Todo o departamento").
    const chamados = [CHAMADO_AREA_INFRA, CHAMADO_ATRIBUIDO_A_MIM];
    const { selecionarFiltro, linhas } = criar(sessaoFalso('rafa.teste'), chamados);

    selecionarFiltro('Minha área: Infraestrutura');

    const restantes = linhas();
    expect(restantes.length).toBe(1);
    expect(restantes[0].textContent).toContain('VPN não conecta');
  });

  it('"Todo o departamento" sempre aparece no filtro, e mostra chamado atribuído a QUALQUER técnico', () => {
    const chamados = [CHAMADO_AREA_SISTEMAS, CHAMADO_ATRIBUIDO_A_MIM, CHAMADO_ATRIBUIDO_A_OUTRO];
    const { opcoesDoFiltro, abrirFiltro, selecionarFiltro, linhas } = criar(
      sessaoFalso('rafa.teste'),
      chamados,
    );

    abrirFiltro();
    expect(opcoesDoFiltro()).toContain('Todo o departamento');

    selecionarFiltro('Todo o departamento');

    expect(linhas().length).toBe(3);
  });

  it('"Todo o departamento" aparece mesmo sem técnico GLPI vinculado à conta logada', () => {
    const { opcoesDoFiltro, abrirFiltro } = criar(sessaoFalso('ninguem.sem.tecnico'));

    abrirFiltro();

    expect(opcoesDoFiltro()).toContain('Todo o departamento');
  });
});
