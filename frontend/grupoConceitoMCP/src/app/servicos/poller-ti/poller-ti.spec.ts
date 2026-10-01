import { HttpDownloadProgressEvent, HttpEventType, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { PollerTi } from './poller-ti';

describe('PollerTi', () => {
  let servico: PollerTi;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    servico = TestBed.inject(PollerTi);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('carrega as etapas e os horários da última/próxima rodada', () => {
    servico.carregar();

    const requisicao = http.expectOne((req) => req.url.endsWith('/api/ti/poller/status'));
    expect(requisicao.request.method).toBe('GET');
    requisicao.flush({
      etapas: [
        { id: 'chamados_novos', rotulo: 'Verificando chamados novos', status: 'concluido', processados: 2 },
        {
          id: 'chamados_aguardando_resposta',
          rotulo: 'Verificando respostas novas',
          status: 'pendente',
          processados: null,
        },
      ],
      ultima_rodada_em: '2026-10-01T12:00:00Z',
      proxima_rodada_em: '2026-10-01T12:05:00Z',
      erro: null,
    });

    expect(servico.etapas().length).toBe(2);
    expect(servico.etapas()[0].processados).toBe(2);
    expect(servico.ultimaRodadaEm()).toBe('2026-10-01T12:00:00Z');
    expect(servico.proximaRodadaEm()).toBe('2026-10-01T12:05:00Z');
    expect(servico.erro()).toBeNull();
  });

  it('expõe o erro da última rodada quando o backend reporta um', () => {
    servico.carregar();

    http.expectOne((req) => req.url.endsWith('/api/ti/poller/status')).flush({
      etapas: [],
      ultima_rodada_em: null,
      proxima_rodada_em: null,
      erro: 'GLPI fora do ar',
    });

    expect(servico.erro()).toBe('GLPI fora do ar');
  });

  it('abre o stream de logs, acumula linhas conforme chegam, e ignora linha vazia (heartbeat)', () => {
    servico.abrirStreamDeLogs();

    const requisicao = http.expectOne((req) => req.url.endsWith('/api/ti/poller/logs'));
    expect(requisicao.request.method).toBe('GET');

    requisicao.event({
      type: HttpEventType.DownloadProgress,
      loaded: 1,
      partialText: '09:58:02 Rodada iniciada\n',
    } as HttpDownloadProgressEvent);
    expect(servico.logs()).toEqual(['09:58:02 Rodada iniciada']);

    // A 2ª linha é o heartbeat (vazia) do backend — não deve virar item.
    requisicao.event({
      type: HttpEventType.DownloadProgress,
      loaded: 2,
      partialText: '09:58:02 Rodada iniciada\n\n09:58:05 Chamado #1 liberado pra Fulano\n',
    } as HttpDownloadProgressEvent);
    expect(servico.logs()).toEqual([
      '09:58:02 Rodada iniciada',
      '09:58:05 Chamado #1 liberado pra Fulano',
    ]);

    servico.fecharStreamDeLogs();
  });

  it('fechar o stream cancela a requisição de verdade e zera as linhas', () => {
    servico.abrirStreamDeLogs();
    const requisicao = http.expectOne((req) => req.url.endsWith('/api/ti/poller/logs'));
    requisicao.event({
      type: HttpEventType.DownloadProgress,
      loaded: 1,
      partialText: '09:58:02 Rodada iniciada\n',
    } as HttpDownloadProgressEvent);
    expect(servico.logs().length).toBe(1);

    servico.fecharStreamDeLogs();

    expect(requisicao.cancelled).toBe(true);
    expect(servico.logs()).toEqual([]);
  });

  it('abrir o stream com uma conexão já aberta não cria uma segunda', () => {
    servico.abrirStreamDeLogs();
    servico.abrirStreamDeLogs();

    http.expectOne((req) => req.url.endsWith('/api/ti/poller/logs'));

    servico.fecharStreamDeLogs();
  });
});
