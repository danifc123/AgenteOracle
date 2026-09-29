import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { IndicadoresTecnico } from './indicadores-tecnico';

interface Resposta {
  meus_chamados: number | null;
  media_chamados_equipe: number;
  meu_tempo_gasto_horas: number | null;
  media_tempo_gasto_equipe_horas: number;
}

function criar(resposta: Resposta) {
  TestBed.configureTestingModule({
    imports: [IndicadoresTecnico],
    providers: [provideHttpClient(), provideHttpClientTesting()],
  });
  const fixture = TestBed.createComponent(IndicadoresTecnico);
  const http = TestBed.inject(HttpTestingController);
  http.expectOne((req) => req.url.endsWith('/api/ti/chamados/meus-indicadores')).flush(resposta);
  fixture.detectChanges();

  return { texto: () => (fixture.nativeElement as HTMLElement).textContent ?? '', nativeElement: fixture.nativeElement };
}

describe('IndicadoresTecnico', () => {
  afterEach(() => TestBed.inject(HttpTestingController).verify());

  it('mostra os 4 números quando o usuário tem técnico vinculado', () => {
    const { texto } = criar({
      meus_chamados: 3,
      media_chamados_equipe: 5.5,
      meu_tempo_gasto_horas: 2,
      media_tempo_gasto_equipe_horas: 4.2,
    });

    expect(texto()).toContain('Seus chamados (30d)');
    expect(texto()).toContain('3');
    expect(texto()).toContain('Média da equipe (chamados)');
    // `app-cartao-kpi` formata número via `toLocaleString('pt-BR')` —
    // vírgula decimal, não ponto.
    expect(texto()).toContain('5,5');
    expect(texto()).toContain('Seu tempo gasto (30d, em horas)');
    expect(texto()).toContain('2');
    expect(texto()).toContain('Média da equipe (tempo, em horas)');
    expect(texto()).toContain('4,2');
  });

  it('destaca "Abaixo da média" pra cada indicador que está abaixo, independente do outro', () => {
    // Chamados abaixo (3 < 5.5), tempo dentro (5 > 4.2).
    const { texto } = criar({
      meus_chamados: 3,
      media_chamados_equipe: 5.5,
      meu_tempo_gasto_horas: 5,
      media_tempo_gasto_equipe_horas: 4.2,
    });

    expect(texto()).toContain('Chamados: Abaixo da média');
    expect(texto()).toContain('Tempo gasto: Dentro da média');
  });

  it('mostra "Dentro da média" nos dois quando o técnico está na média ou acima dos dois', () => {
    const { texto } = criar({
      meus_chamados: 7,
      media_chamados_equipe: 5,
      meu_tempo_gasto_horas: 6,
      media_tempo_gasto_equipe_horas: 4,
    });

    expect(texto()).toContain('Chamados: Dentro da média');
    expect(texto()).toContain('Tempo gasto: Dentro da média');
  });

  it('não renderiza nada quando o usuário não tem técnico vinculado', () => {
    const { nativeElement } = criar({
      meus_chamados: null,
      media_chamados_equipe: 4.2,
      meu_tempo_gasto_horas: null,
      media_tempo_gasto_equipe_horas: 1.5,
    });

    expect((nativeElement as HTMLElement).querySelector('.secao-indicadores')).toBeNull();
  });
});
