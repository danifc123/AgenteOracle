import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { WidgetChamadosTotal } from './widget-chamados-total';

function criar(chamados: { status: string }[]) {
  TestBed.configureTestingModule({
    imports: [WidgetChamadosTotal],
    providers: [provideHttpClient(), provideHttpClientTesting()],
  });
  const fixture = TestBed.createComponent(WidgetChamadosTotal);
  const http = TestBed.inject(HttpTestingController);
  http.expectOne((req) => req.url.endsWith('/api/ti/chamados')).flush(chamados);
  fixture.detectChanges();

  return { texto: () => (fixture.nativeElement as HTMLElement).textContent ?? '' };
}

describe('WidgetChamadosTotal', () => {
  afterEach(() => TestBed.inject(HttpTestingController).verify());

  it('mostra o total de chamados em aberto', () => {
    const { texto } = criar([{ status: 'novo' }, { status: 'novo' }, { status: 'aguardando_usuario' }]);

    expect(texto()).toContain('Chamados em aberto');
    expect(texto()).toContain('3');
  });

  it('sem nenhum chamado, mostra zero', () => {
    const { texto } = criar([]);

    expect(texto()).toContain('0');
  });
});
