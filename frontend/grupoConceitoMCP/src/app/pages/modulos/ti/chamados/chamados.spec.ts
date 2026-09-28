import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { vi } from 'vitest';
import { ConfiguracoesTi } from '../../../../servicos/configuracoes-ti/configuracoes-ti';
import { Sessao } from '../../../../servicos/sessao/sessao';
import { Chamado, ChamadosTi } from './chamados';

// `tecnico_atribuido` fica `null` nos três de propósito: na tela real ele só
// é preenchido no instante em que o chamado vira `fila_atendimento` — status
// que o backend já filtra fora daqui (`_precisa_atencao`) — então nunca
// aparece atribuído nesta lista. O filtro "Meus chamados" usa `area`.
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

function criar(sessao = sessaoFalso()) {
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

  http.expectOne((req) => req.url.endsWith('/api/ti/chamados')).flush([
    CHAMADO_AREA_SISTEMAS,
    CHAMADO_AREA_INFRA,
    CHAMADO_AREA_SISTEMAS_2,
  ]);
  http.expectOne((req) => req.url.endsWith('/api/ti/tecnicos')).flush([
    { identificador: '111', nome: 'Rafa Teste', usuario: 'rafa.teste', area: 'infra' },
    { identificador: '222', nome: 'Outro Técnico', usuario: 'outro.tecnico', area: 'sistemas' },
    // Área 'processos': nenhum dos 3 chamados é dessa área — testa o
    // estado vazio do FILTRO (diferente de não ter técnico vinculado
    // nenhum, que já desabilita o botão antes de chegar aqui).
    { identificador: '333', nome: 'Sem Chamado', usuario: 'sem.chamado', area: 'processos' },
  ]);
  fixture.detectChanges();

  const el: HTMLElement = fixture.nativeElement;

  return {
    fixture,
    http,
    el,
    linhas: () => Array.from(el.querySelectorAll('table tbody tr')) as HTMLElement[],
    botaoMeusChamados: () =>
      Array.from(el.querySelectorAll('button')).find((b) => b.textContent?.includes('Meus chamados')) as
        | HTMLButtonElement
        | undefined,
    clicarMeusChamados: () => {
      (
        Array.from(el.querySelectorAll('button')).find((b) => b.textContent?.includes('Meus chamados')) as HTMLButtonElement
      ).click();
      fixture.detectChanges();
    },
  };
}

describe('ChamadosTi', () => {
  afterEach(() => {
    TestBed.inject(HttpTestingController).verify();
  });

  it('carrega e mostra todos os chamados por padrão', () => {
    const { linhas } = criar();

    expect(linhas().length).toBe(3);
  });

  it('o botão "Meus chamados" fica habilitado quando a conta logada tem técnico do GLPI vinculado', () => {
    const { botaoMeusChamados } = criar(sessaoFalso('rafa.teste'));

    expect(botaoMeusChamados()?.disabled).toBe(false);
  });

  it('o botão "Meus chamados" fica desabilitado quando a conta logada não tem técnico vinculado', () => {
    const { botaoMeusChamados } = criar(sessaoFalso('ninguem.sem.tecnico'));

    expect(botaoMeusChamados()?.disabled).toBe(true);
  });

  it('clicar em "Meus chamados" mostra só os chamados da área do técnico logado', () => {
    const { clicarMeusChamados, linhas } = criar(sessaoFalso('rafa.teste'));

    clicarMeusChamados();

    const restantes = linhas();
    expect(restantes.length).toBe(1);
    expect(restantes[0].textContent).toContain('VPN não conecta');
  });

  it('clicar de novo em "Meus chamados" volta a mostrar todos', () => {
    const { clicarMeusChamados, linhas } = criar(sessaoFalso('rafa.teste'));

    clicarMeusChamados();
    clicarMeusChamados();

    expect(linhas().length).toBe(3);
  });

  it('conta logada com técnico cuja área não tem nenhum chamado mostra o estado vazio do filtro, não a tabela', () => {
    const { clicarMeusChamados, linhas, el } = criar(sessaoFalso('sem.chamado'));

    clicarMeusChamados();

    expect(linhas().length).toBe(0);
    expect(el.textContent).toContain('Nenhum chamado da sua área no momento.');
  });
});
