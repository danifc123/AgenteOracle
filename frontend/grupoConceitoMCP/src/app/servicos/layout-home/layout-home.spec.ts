import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { ItemLayoutHome } from '../../pages/home/catalogo-widgets-home';
import { TOAST_DESATIVADO } from '../toast.interceptor/toast.interceptor';
import { LayoutHome } from './layout-home';

function item(id: string, tamanho: ItemLayoutHome['tamanho'] = 'pequeno'): ItemLayoutHome {
  return { id, tamanho };
}

describe('LayoutHome', () => {
  let servico: LayoutHome;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    servico = TestBed.inject(LayoutHome);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
    vi.useRealTimers();
  });

  it('deveria carregar o layout com GET e atualizar o signal', () => {
    servico.carregar();

    const requisicao = http.expectOne((req) => req.url.endsWith('/api/home/dashboard'));
    requisicao.flush({ widgets: [item('ti:chamados_total'), item('financeiro:saldo_projetado')] });

    expect(requisicao.request.method).toBe('GET');
    expect(servico.widgets()).toEqual([item('ti:chamados_total'), item('financeiro:saldo_projetado')]);
  });

  it('salvarAgora deveria enviar PUT na hora, sem toast automático', () => {
    servico.salvarAgora([item('ti:chamados_total', 'grande')]);

    const requisicao = http.expectOne((req) => req.url.endsWith('/api/home/dashboard'));
    requisicao.flush({ widgets: [item('ti:chamados_total', 'grande')] });

    expect(requisicao.request.method).toBe('PUT');
    expect(requisicao.request.body).toEqual({ widgets: [item('ti:chamados_total', 'grande')] });
    expect(requisicao.request.context.get(TOAST_DESATIVADO)).toBe(true);
  });

  it('salvarAgora deveria atualizar o signal otimisticamente antes da resposta', () => {
    servico.salvarAgora([item('ti:chamados_total')]);

    expect(servico.widgets()).toEqual([item('ti:chamados_total')]);

    http.expectOne((req) => req.method === 'PUT').flush({ widgets: [item('ti:chamados_total')] });
  });

  it('agendarSalvar NÃO deveria disparar PUT antes do debounce', () => {
    vi.useFakeTimers();

    servico.agendarSalvar([item('ti:chamados_total'), item('financeiro:saldo_projetado')]);
    vi.advanceTimersByTime(200);

    http.expectNone((req) => req.method === 'PUT');
    expect(servico.widgets()).toEqual([item('ti:chamados_total'), item('financeiro:saldo_projetado')]);
  });

  it('agendarSalvar deveria disparar só 1 PUT mesmo com várias chamadas seguidas (simula arrastar)', () => {
    vi.useFakeTimers();

    servico.agendarSalvar([item('ti:chamados_total')]);
    vi.advanceTimersByTime(200);
    servico.agendarSalvar([item('financeiro:saldo_projetado')]);
    vi.advanceTimersByTime(200);
    servico.agendarSalvar([item('financeiro:saldo_projetado'), item('ti:chamados_total')]);
    vi.advanceTimersByTime(600);

    const requisicao = http.expectOne((req) => req.method === 'PUT');
    expect(requisicao.request.body).toEqual({
      widgets: [item('financeiro:saldo_projetado'), item('ti:chamados_total')],
    });
    requisicao.flush({ widgets: [item('financeiro:saldo_projetado'), item('ti:chamados_total')] });
  });
});
