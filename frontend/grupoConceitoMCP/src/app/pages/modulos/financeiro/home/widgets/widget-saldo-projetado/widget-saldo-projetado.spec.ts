import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { WidgetSaldoProjetado } from './widget-saldo-projetado';

function criar() {
  TestBed.configureTestingModule({
    imports: [WidgetSaldoProjetado],
    providers: [provideHttpClient(), provideHttpClientTesting()],
  });
  const fixture = TestBed.createComponent(WidgetSaldoProjetado);
  const http = TestBed.inject(HttpTestingController);

  return { fixture, http, texto: () => (fixture.nativeElement as HTMLElement).textContent ?? '' };
}

function flushFiliais(http: HttpTestingController, codigos: string[]): void {
  http
    .expectOne((req) => req.url.endsWith('/api/financeiro/filiais'))
    .flush(codigos.map((codigo) => ({ codigo, nome: codigo })));
}

function flushPrevisao(http: HttpTestingController, totalAReceber: number, totalAPagar: number): void {
  http.expectOne((req) => req.url.endsWith('/api/financeiro/previsao/fluxo-caixa')).flush(
    `${JSON.stringify({
      tipo: 'resultado',
      dados: {
        fatias_a_receber: [{ nome: 'No período', valor: totalAReceber }],
        fatias_a_pagar: [{ nome: 'No período', valor: totalAPagar }],
      },
    })}\n`,
  );
}

describe('WidgetSaldoProjetado', () => {
  afterEach(() => TestBed.inject(HttpTestingController).verify());

  it('pede a previsão com todas as filiais liberadas e mostra a receber menos a pagar', async () => {
    const { fixture, http, texto } = criar();

    flushFiliais(http, ['01', '02']);
    const requisicaoPrevisao = http.expectOne((req) => req.url.endsWith('/api/financeiro/previsao/fluxo-caixa'));
    expect(requisicaoPrevisao.request.params.get('filial')).toBe('01,02');
    requisicaoPrevisao.flush(
      `${JSON.stringify({
        tipo: 'resultado',
        dados: { fatias_a_receber: [{ valor: 1000 }], fatias_a_pagar: [{ valor: 400 }] },
      })}\n`,
    );
    await fixture.whenStable();
    fixture.detectChanges();

    expect(texto()).toContain('Saldo projetado');
    expect(texto()).toContain('600');
  });

  it('sem nenhuma filial liberada, não chama a previsão e mostra zero', () => {
    const { fixture, http, texto } = criar();

    flushFiliais(http, []);
    fixture.detectChanges();

    http.expectNone((req) => req.url.endsWith('/api/financeiro/previsao/fluxo-caixa'));
    expect(texto()).toContain('0');
  });

  it('saldo negativo (mais a pagar que a receber) mostra o número negativo', async () => {
    const { fixture, http, texto } = criar();

    flushFiliais(http, ['01']);
    flushPrevisao(http, 200, 900);
    await fixture.whenStable();
    fixture.detectChanges();

    expect(texto()).toContain('-700');
  });
});
