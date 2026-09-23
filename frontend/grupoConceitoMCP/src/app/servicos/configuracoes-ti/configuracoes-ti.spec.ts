import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { TOAST_DESATIVADO } from '../toast.interceptor/toast.interceptor';
import { ConfiguracoesTi, ConfiguracoesTiResposta } from './configuracoes-ti';

const RESPOSTA: ConfiguracoesTiResposta = {
  usar_ia_avaliacao_chamado: false,
  percentual_amostragem_chamados: 20,
  percentual_alterado_em: '2026-09-21T14:41:00Z',
  ler_chamados_antigos: true,
  teto_tokens_diario: 50000,
};

describe('ConfiguracoesTi', () => {
  let servico: ConfiguracoesTi;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    servico = TestBed.inject(ConfiguracoesTi);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('deveria enviar PATCH só com as chaves alteradas e sem toast automático', () => {
    servico.salvar({ percentual_amostragem_chamados: 20 }).subscribe();

    const requisicao = http.expectOne((req) => req.url.endsWith('/api/ti/configuracoes'));
    requisicao.flush(RESPOSTA);

    expect(requisicao.request.method).toBe('PATCH');
    expect(requisicao.request.body).toEqual({ percentual_amostragem_chamados: 20 });
    expect(requisicao.request.context.get(TOAST_DESATIVADO)).toBe(true);
  });

  it('deveria atualizar os signals com a resposta do servidor ao salvar', () => {
    servico.salvar({ ler_chamados_antigos: true }).subscribe();

    http.expectOne((req) => req.method === 'PATCH').flush(RESPOSTA);

    expect(servico.usarIaAvaliacaoChamado()).toBe(false);
    expect(servico.percentualAmostragemChamados()).toBe(20);
    expect(servico.percentualAlteradoEm()).toBe('2026-09-21T14:41:00Z');
    expect(servico.lerChamadosAntigos()).toBe(true);
    expect(servico.tetoTokensDiario()).toBe(50000);
  });

  it('deveria manter os signals quando o servidor recusa a alteração', () => {
    servico.salvar({ percentual_amostragem_chamados: 20 }).subscribe({ error: () => undefined });

    http
      .expectOne((req) => req.method === 'PATCH')
      .flush(
        { erro: 'Acesso restrito a desenvolvedores.' },
        { status: 403, statusText: 'Forbidden' },
      );

    expect(servico.percentualAmostragemChamados()).toBe(100);
  });

  it('deveria carregar as configurações com GET e atualizar os signals', () => {
    servico.carregar();

    const requisicao = http.expectOne((req) => req.url.endsWith('/api/ti/configuracoes'));
    requisicao.flush(RESPOSTA);

    expect(requisicao.request.method).toBe('GET');
    expect(servico.percentualAmostragemChamados()).toBe(20);
  });
});
