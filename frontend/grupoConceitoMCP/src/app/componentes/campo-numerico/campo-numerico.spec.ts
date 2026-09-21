import { TestBed } from '@angular/core/testing';
import { CampoNumerico } from './campo-numerico';

function criar(entradas: Record<string, unknown> = {}) {
  const fixture = TestBed.createComponent(CampoNumerico);
  fixture.componentRef.setInput('rotulo', 'Chamados analisados');
  for (const [nome, valor] of Object.entries(entradas)) {
    fixture.componentRef.setInput(nome, valor);
  }
  fixture.detectChanges();
  const input: HTMLInputElement = fixture.nativeElement.querySelector('input');
  return { fixture, input };
}

describe('CampoNumerico', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [CampoNumerico] }).compileComponents();
  });

  it('liga o rótulo ao campo e mostra o valor informado', () => {
    const { fixture, input } = criar({ valor: '20' });

    const rotulo: HTMLLabelElement = fixture.nativeElement.querySelector('label');
    expect(rotulo.textContent).toContain('Chamados analisados');
    expect(rotulo.htmlFor).toBe(input.id);
    expect(input.value).toBe('20');
  });

  it('mostra o sufixo ao lado do campo', () => {
    const { fixture } = criar({ sufixo: '%' });

    expect(fixture.nativeElement.querySelector('.sufixo').textContent.trim()).toBe('%');
  });

  it('sem sufixo não renderiza o elemento', () => {
    const { fixture } = criar();

    expect(fixture.nativeElement.querySelector('.sufixo')).toBeNull();
  });

  it('usa teclado numérico decimal', () => {
    const { input } = criar();

    expect(input.getAttribute('inputmode')).toBe('decimal');
  });

  it('emite o texto digitado a cada alteração', () => {
    const { fixture, input } = criar();
    const emitidos: string[] = [];
    fixture.componentInstance.valorChange.subscribe((texto) => emitidos.push(texto));

    input.value = '33,3';
    input.dispatchEvent(new Event('input'));

    expect(emitidos).toEqual(['33,3']);
  });

  it('mostra o erro como alerta e marca o campo como inválido', () => {
    const { fixture, input } = criar({ erro: 'Informe um número de 0 a 100.' });

    const alerta = fixture.nativeElement.querySelector('[role="alert"]');
    expect(alerta.textContent).toContain('Informe um número de 0 a 100.');
    expect(input.getAttribute('aria-invalid')).toBe('true');
    expect(input.getAttribute('aria-describedby')).toContain(alerta.id);
  });

  it('sem erro não há alerta e o campo é válido', () => {
    const { fixture, input } = criar();

    expect(fixture.nativeElement.querySelector('[role="alert"]')).toBeNull();
    expect(input.getAttribute('aria-invalid')).toBe('false');
  });

  it('a descrição fica ligada ao campo por aria-describedby', () => {
    const { fixture, input } = criar({ descricao: 'Ex.: 20 = 2 de cada 10.' });

    const descricao = fixture.nativeElement.querySelector('.descricao');
    expect(descricao.textContent).toContain('Ex.: 20 = 2 de cada 10.');
    expect(input.getAttribute('aria-describedby')).toContain(descricao.id);
  });

  it('desabilitado bloqueia o campo', () => {
    const { input } = criar({ desabilitado: true });

    expect(input.disabled).toBe(true);
  });
});
