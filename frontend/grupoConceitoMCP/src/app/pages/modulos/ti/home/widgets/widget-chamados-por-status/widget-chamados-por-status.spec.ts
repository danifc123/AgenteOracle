import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { WidgetChamadosPorStatus } from './widget-chamados-por-status';

function criar(chamados: { status: string }[]) {
  TestBed.configureTestingModule({
    imports: [WidgetChamadosPorStatus],
    providers: [provideHttpClient(), provideHttpClientTesting()],
  });
  const fixture = TestBed.createComponent(WidgetChamadosPorStatus);
  const http = TestBed.inject(HttpTestingController);
  http.expectOne((req) => req.url.endsWith('/api/ti/chamados')).flush(chamados);
  fixture.detectChanges();

  return {
    fixture,
    texto: () => (fixture.nativeElement as HTMLElement).textContent ?? '',
  };
}

describe('WidgetChamadosPorStatus', () => {
  afterEach(() => TestBed.inject(HttpTestingController).verify());

  it('sem chamado em aberto, mostra a mensagem de "tudo em dia"', () => {
    const { texto } = criar([]);

    expect(texto()).toContain('Nenhum chamado em aberto agora');
  });

  it('com chamado em aberto, mostra o gráfico por status', () => {
    const { fixture } = criar([{ status: 'novo' }, { status: 'aguardando_usuario' }]);

    expect(fixture.nativeElement.querySelector('app-grafico-rosca')).not.toBeNull();
  });
});
