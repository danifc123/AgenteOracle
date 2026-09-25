import { TestBed } from '@angular/core/testing';
import { CartaoResultado } from './cartao-resultado';

describe('CartaoResultado', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [CartaoResultado] }).compileComponents();
  });

  it('não aplica a classe de destaque por padrão', () => {
    const fixture = TestBed.createComponent(CartaoResultado);
    fixture.detectChanges();

    const cartao = fixture.nativeElement.querySelector('.cartao-resultado');
    expect(cartao.classList).not.toContain('cartao-resultado--destaque');
  });

  it('aplica a classe de destaque quando destaque=true', () => {
    const fixture = TestBed.createComponent(CartaoResultado);
    fixture.componentRef.setInput('destaque', true);
    fixture.detectChanges();

    const cartao = fixture.nativeElement.querySelector('.cartao-resultado');
    expect(cartao.classList).toContain('cartao-resultado--destaque');
  });
});
