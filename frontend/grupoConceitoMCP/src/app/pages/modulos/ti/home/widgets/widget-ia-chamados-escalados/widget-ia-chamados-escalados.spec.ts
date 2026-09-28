import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { ChamadosIaResposta, UsoIa } from '../../../../../../servicos/uso-ia/uso-ia';
import { WidgetIaChamadosEscalados } from './widget-ia-chamados-escalados';

const CHAMADOS_IA: ChamadosIaResposta = {
  total_chamados: 10,
  avaliados_insuficientes: 2,
  com_fallback_embedding: 1,
  duracao_media_ms: 500,
};

function criar(chamadosIa: ChamadosIaResposta | null) {
  TestBed.configureTestingModule({
    imports: [WidgetIaChamadosEscalados],
    providers: [
      { provide: UsoIa, useValue: { tokensHojePorDominio: signal({}), chamadosIa: signal(chamadosIa), carregar: vi.fn() } },
    ],
  });
  const fixture = TestBed.createComponent(WidgetIaChamadosEscalados);
  fixture.detectChanges();

  return { texto: () => (fixture.nativeElement as HTMLElement).textContent ?? '' };
}

describe('WidgetIaChamadosEscalados', () => {
  it('mostra quantos chamados foram escalados pra humano', () => {
    const { texto } = criar(CHAMADOS_IA);

    expect(texto()).toContain('Escalados pra humano (30d)');
    expect(texto()).toContain('2');
  });
});
