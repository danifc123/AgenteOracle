import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { ChamadosIaResposta, UsoIa } from '../../../../../../servicos/uso-ia/uso-ia';
import { WidgetIaChamadosAvaliados } from './widget-ia-chamados-avaliados';

const CHAMADOS_IA: ChamadosIaResposta = {
  total_chamados: 10,
  avaliados_insuficientes: 2,
  com_fallback_embedding: 1,
  duracao_media_ms: 500,
};

function criar(chamadosIa: ChamadosIaResposta | null) {
  TestBed.configureTestingModule({
    imports: [WidgetIaChamadosAvaliados],
    providers: [
      { provide: UsoIa, useValue: { tokensHojePorDominio: signal({}), chamadosIa: signal(chamadosIa), carregar: vi.fn() } },
    ],
  });
  const fixture = TestBed.createComponent(WidgetIaChamadosAvaliados);
  fixture.detectChanges();

  return { texto: () => (fixture.nativeElement as HTMLElement).textContent ?? '' };
}

describe('WidgetIaChamadosAvaliados', () => {
  it('mostra o total de chamados avaliados pela IA', () => {
    const { texto } = criar(CHAMADOS_IA);

    expect(texto()).toContain('Chamados avaliados pela IA (30d)');
    expect(texto()).toContain('10');
  });

  it('sem dado carregado ainda, não renderiza nada', () => {
    const { texto } = criar(null);

    expect(texto()).toBe('');
  });
});
