import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { WidgetFaturamentoTotal } from './widget-faturamento-total';

function criar() {
  TestBed.configureTestingModule({
    imports: [WidgetFaturamentoTotal],
    providers: [provideHttpClient(), provideHttpClientTesting()],
  });
  const fixture = TestBed.createComponent(WidgetFaturamentoTotal);
  const http = TestBed.inject(HttpTestingController);

  return { fixture, http, texto: () => (fixture.nativeElement as HTMLElement).textContent ?? '' };
}

function flushFiliais(http: HttpTestingController, codigos: string[]): void {
  http
    .expectOne((req) => req.url.endsWith('/api/financeiro/filiais'))
    .flush(codigos.map((codigo) => ({ codigo, nome: codigo })));
}

describe('WidgetFaturamentoTotal', () => {
  afterEach(() => TestBed.inject(HttpTestingController).verify());

  it('pede a previsão com todas as filiais liberadas e soma o histórico', async () => {
    const { fixture, http, texto } = criar();

    flushFiliais(http, ['01', '02']);
    const requisicaoPrevisao = http.expectOne((req) => req.url.endsWith('/api/financeiro/previsao/vendas'));
    expect(requisicaoPrevisao.request.params.get('filial')).toBe('01,02');
    requisicaoPrevisao.flush(
      `${JSON.stringify({
        tipo: 'resultado',
        dados: { historico: [{ mes: '2026-07', valor: 1000 }, { mes: '2026-08', valor: 1500 }] },
      })}\n`,
    );
    await fixture.whenStable();
    fixture.detectChanges();

    expect(texto()).toContain('Faturamento total');
    expect(texto()).toContain('2,5');
  });

  it('sem nenhuma filial liberada, não chama a previsão e mostra zero', () => {
    const { fixture, http, texto } = criar();

    flushFiliais(http, []);
    fixture.detectChanges();

    http.expectNone((req) => req.url.endsWith('/api/financeiro/previsao/vendas'));
    expect(texto()).toContain('0');
  });
});
