import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { ItemLayoutTi } from '../../pages/modulos/ti/home/widgets/catalogo-widgets-ti';
import { TOAST_DESATIVADO } from '../toast.interceptor/toast.interceptor';
import { LayoutDashboardTi } from './layout-dashboard-ti';

function item(id: ItemLayoutTi['id'], tamanho: ItemLayoutTi['tamanho'] = 'pequeno'): ItemLayoutTi {
  return { id, tamanho };
}

describe('LayoutDashboardTi', () => {
  let servico: LayoutDashboardTi;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    servico = TestBed.inject(LayoutDashboardTi);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
    vi.useRealTimers();
  });

  it('deveria carregar o layout com GET e atualizar o signal', () => {
    servico.carregar();

    const requisicao = http.expectOne((req) => req.url.endsWith('/api/ti/dashboard'));
    requisicao.flush({ widgets: [item('chamados_total'), item('ia_tokens_hoje')] });

    expect(requisicao.request.method).toBe('GET');
    expect(servico.widgets()).toEqual([item('chamados_total'), item('ia_tokens_hoje')]);
  });

  it('salvarAgora deveria enviar PUT na hora, sem toast automático', () => {
    servico.salvarAgora([item('chamados_total', 'grande')]);

    const requisicao = http.expectOne((req) => req.url.endsWith('/api/ti/dashboard'));
    requisicao.flush({ widgets: [item('chamados_total', 'grande')] });

    expect(requisicao.request.method).toBe('PUT');
    expect(requisicao.request.body).toEqual({ widgets: [item('chamados_total', 'grande')] });
    expect(requisicao.request.context.get(TOAST_DESATIVADO)).toBe(true);
  });

  it('salvarAgora deveria atualizar o signal otimisticamente antes da resposta', () => {
    servico.salvarAgora([item('chamados_total')]);

    expect(servico.widgets()).toEqual([item('chamados_total')]);

    http.expectOne((req) => req.method === 'PUT').flush({ widgets: [item('chamados_total')] });
  });

  it('agendarSalvar NÃO deveria disparar PUT antes do debounce', () => {
    vi.useFakeTimers();

    servico.agendarSalvar([item('chamados_total'), item('chamados_por_status')]);
    vi.advanceTimersByTime(200);

    http.expectNone((req) => req.method === 'PUT');
    expect(servico.widgets()).toEqual([item('chamados_total'), item('chamados_por_status')]);
  });

  it('agendarSalvar deveria disparar só 1 PUT mesmo com várias chamadas seguidas (simula arrastar)', () => {
    vi.useFakeTimers();

    servico.agendarSalvar([item('chamados_total')]);
    vi.advanceTimersByTime(200);
    servico.agendarSalvar([item('chamados_por_status')]);
    vi.advanceTimersByTime(200);
    servico.agendarSalvar([item('chamados_por_status'), item('chamados_total')]);
    vi.advanceTimersByTime(600);

    const requisicao = http.expectOne((req) => req.method === 'PUT');
    expect(requisicao.request.body).toEqual({ widgets: [item('chamados_por_status'), item('chamados_total')] });
    requisicao.flush({ widgets: [item('chamados_por_status'), item('chamados_total')] });
  });
});
