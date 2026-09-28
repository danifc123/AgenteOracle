import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { ChamadosIaResposta, UsoIa } from '../../../../../../servicos/uso-ia/uso-ia';
import { WidgetIaCategoriaNaoCorrigida } from './widget-ia-categoria-nao-corrigida';

const CHAMADOS_IA: ChamadosIaResposta = {
  total_chamados: 10,
  avaliados_insuficientes: 2,
  com_fallback_embedding: 1,
  duracao_media_ms: 500,
};

function criar(chamadosIa: ChamadosIaResposta | null) {
  TestBed.configureTestingModule({
    imports: [WidgetIaCategoriaNaoCorrigida],
    providers: [
      { provide: UsoIa, useValue: { tokensHojePorDominio: signal({}), chamadosIa: signal(chamadosIa), carregar: vi.fn() } },
    ],
  });
  const fixture = TestBed.createComponent(WidgetIaCategoriaNaoCorrigida);
  fixture.detectChanges();

  return { texto: () => (fixture.nativeElement as HTMLElement).textContent ?? '' };
}

describe('WidgetIaCategoriaNaoCorrigida', () => {
  it('mostra quantos chamados ficaram sem correção automática de categoria por falta de embedding', () => {
    const { texto } = criar(CHAMADOS_IA);

    expect(texto()).toContain('Categoria não corrigida automaticamente (30d)');
    expect(texto()).toContain('1');
  });
});
