import { TestBed } from '@angular/core/testing';
import { Interruptor } from './interruptor';

function criar(entradas: Record<string, unknown> = {}) {
  const fixture = TestBed.createComponent(Interruptor);
  fixture.componentRef.setInput('rotulo', 'Ler chamados antigos');
  for (const [nome, valor] of Object.entries(entradas)) {
    fixture.componentRef.setInput(nome, valor);
  }
  fixture.detectChanges();
  const botao: HTMLButtonElement = fixture.nativeElement.querySelector('button');
  return { fixture, botao };
}

describe('Interruptor', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [Interruptor] }).compileComponents();
  });

  it('renderiza rótulo e descrição', () => {
    const { fixture } = criar({ descricao: 'Texto de apoio' });

    const texto = fixture.nativeElement.textContent;
    expect(texto).toContain('Ler chamados antigos');
    expect(texto).toContain('Texto de apoio');
  });

  it('é um switch acessível ligado ao rótulo e à descrição', () => {
    const { botao } = criar({ descricao: 'Texto de apoio' });

    expect(botao.getAttribute('role')).toBe('switch');
    const rotulo = botao.getAttribute('aria-labelledby') ?? '';
    const descricao = botao.getAttribute('aria-describedby') ?? '';
    expect(botao.querySelector(`[id="${rotulo}"]`)?.textContent).toContain('Ler chamados antigos');
    expect(botao.querySelector(`[id="${descricao}"]`)?.textContent).toContain('Texto de apoio');
  });

  it('sem descrição não declara aria-describedby', () => {
    const { botao } = criar();

    expect(botao.hasAttribute('aria-describedby')).toBe(false);
  });

  it.each([
    [false, 'false'],
    [true, 'true'],
  ])('marcado=%s vira aria-checked=%s', (marcado, esperado) => {
    const { botao } = criar({ marcado });

    expect(botao.getAttribute('aria-checked')).toBe(esperado);
  });

  it.each([
    [false, true],
    [true, false],
  ])('clicar com marcado=%s emite %s', (marcado, esperado) => {
    const { fixture, botao } = criar({ marcado });
    const emitidos: boolean[] = [];
    fixture.componentInstance.alterado.subscribe((valor) => emitidos.push(valor));

    botao.click();

    expect(emitidos).toEqual([esperado]);
  });

  it('desabilitado não emite nada ao clicar', () => {
    const { fixture, botao } = criar({ desabilitado: true });
    const emitidos: boolean[] = [];
    fixture.componentInstance.alterado.subscribe((valor) => emitidos.push(valor));

    botao.click();

    expect(botao.disabled).toBe(true);
    expect(emitidos).toEqual([]);
  });

  it('cada interruptor tem ids próprios (dois na mesma tela não se misturam)', () => {
    const primeiro = criar().botao.getAttribute('aria-labelledby');
    const segundo = criar().botao.getAttribute('aria-labelledby');

    expect(primeiro).not.toBe(segundo);
  });
});
