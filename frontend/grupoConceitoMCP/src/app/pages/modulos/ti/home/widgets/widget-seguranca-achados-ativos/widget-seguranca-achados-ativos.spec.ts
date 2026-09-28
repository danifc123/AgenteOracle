import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { WidgetSegurancaAchadosAtivos } from './widget-seguranca-achados-ativos';

function criar(achados: unknown[]) {
  TestBed.configureTestingModule({
    imports: [WidgetSegurancaAchadosAtivos],
    providers: [provideHttpClient(), provideHttpClientTesting()],
  });
  const fixture = TestBed.createComponent(WidgetSegurancaAchadosAtivos);
  const http = TestBed.inject(HttpTestingController);
  http.expectOne((req) => req.url.endsWith('/api/ti/seguranca/historico')).flush(achados);
  fixture.detectChanges();

  return { texto: () => (fixture.nativeElement as HTMLElement).textContent ?? '' };
}

describe('WidgetSegurancaAchadosAtivos', () => {
  afterEach(() => TestBed.inject(HttpTestingController).verify());

  it('mostra a quantidade de achados de segurança ativos', () => {
    const { texto } = criar([{ usuario: 'a' }, { usuario: 'b' }]);

    expect(texto()).toContain('Achados de segurança ativos');
    expect(texto()).toContain('2');
  });

  it('sem nenhum achado, mostra zero', () => {
    const { texto } = criar([]);

    expect(texto()).toContain('0');
  });
});
