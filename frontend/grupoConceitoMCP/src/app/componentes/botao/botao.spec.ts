import { TestBed } from '@angular/core/testing';
import { Botao } from './botao';

describe('Botao', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [Botao] }).compileComponents();
  });

  it('sem title informado, não tem atributo title nenhum no DOM (nunca o texto "null")', () => {
    // Regressão: `[title]="title()"` era bind de PROPRIEDADE — com
    // `title()` devolvendo `null` (padrão do input), o DOM converte pra
    // string literal "null" em vez de remover o atributo (`.title = null`
    // não tem tratamento especial de null, diferente de `removeAttribute`).
    // Corrigido trocando pra `[attr.title]`, que remove o atributo de
    // verdade quando o valor é `null`.
    const fixture = TestBed.createComponent(Botao);
    fixture.detectChanges();

    const botao = fixture.nativeElement.querySelector('button');
    expect(botao.hasAttribute('title')).toBe(false);
    expect(botao.title).not.toBe('null');
  });

  it('com title informado, o atributo title reflete o texto certo', () => {
    const fixture = TestBed.createComponent(Botao);
    fixture.componentRef.setInput('title', 'Remover item');
    fixture.detectChanges();

    const botao = fixture.nativeElement.querySelector('button');
    expect(botao.getAttribute('title')).toBe('Remover item');
  });
});
