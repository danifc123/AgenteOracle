import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { UsoIa } from '../../../../../../servicos/uso-ia/uso-ia';
import { WidgetIaTokensHoje } from './widget-ia-tokens-hoje';

function criar(tokensHojePorDominio: Record<string, number>) {
  TestBed.configureTestingModule({
    imports: [WidgetIaTokensHoje],
    providers: [
      {
        provide: UsoIa,
        useValue: { tokensHojePorDominio: signal(tokensHojePorDominio), chamadosIa: signal(null), carregar: vi.fn() },
      },
    ],
  });
  const fixture = TestBed.createComponent(WidgetIaTokensHoje);
  fixture.detectChanges();

  return { texto: () => (fixture.nativeElement as HTMLElement).textContent ?? '' };
}

describe('WidgetIaTokensHoje', () => {
  it('soma os tokens de todos os domínios', () => {
    const { texto } = criar({ ti: 300, rh: 200 });

    expect(texto()).toContain('Tokens hoje');
    expect(texto()).toContain('500');
  });
});
