import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { PassoTour, TourGuiado } from './tour-guiado';

const PASSOS: PassoTour[] = [
  { alvo: '[data-teste-alvo="um"]', titulo: 'Passo um', descricao: 'Descrição do passo um' },
  { alvo: '[data-teste-alvo="dois"]', titulo: 'Passo dois', descricao: 'Descrição do passo dois' },
  { alvo: '[data-teste-alvo="tres"]', titulo: 'Passo três', descricao: 'Descrição do passo três' },
];

/** `document.querySelector` busca no documento de verdade, não só no
 * fixture — os alvos precisam existir de fato no `document.body`, como
 * aconteceria nos campos reais de um formulário. */
function criarAlvos(chaves: string[]): HTMLElement[] {
  return chaves.map((chave) => {
    const elemento = document.createElement('div');
    elemento.setAttribute('data-teste-alvo', chave);
    document.body.appendChild(elemento);
    return elemento;
  });
}

function criar(passos: PassoTour[] = PASSOS) {
  TestBed.configureTestingModule({ imports: [TourGuiado] });
  const fixture = TestBed.createComponent(TourGuiado);
  const fechados: number[] = [];
  // Assina ANTES do primeiro `detectChanges()` — se nenhum alvo existir,
  // o próprio `effect()` do componente já emite `fechar` síncrono nesse
  // primeiro ciclo, e uma assinatura tardia perderia essa emissão.
  fixture.componentInstance.fechar.subscribe(() => fechados.push(1));
  fixture.componentRef.setInput('passos', passos);
  fixture.componentRef.setInput('aberto', true);
  fixture.detectChanges();

  const el: HTMLElement = fixture.nativeElement;

  return {
    fixture,
    fechou: () => fechados.length > 0,
    texto: () => el.textContent ?? '',
    botao: (rotulo: string) =>
      Array.from(el.querySelectorAll('button')).find((b) => b.textContent?.trim() === rotulo) as
        | HTMLButtonElement
        | undefined,
    destaqueEstaAnimando: () => el.querySelector('.destaque')?.classList.contains('destaque--animado') ?? false,
  };
}

describe('TourGuiado', () => {
  let alvosCriados: HTMLElement[] = [];

  afterEach(() => {
    alvosCriados.forEach((elemento) => elemento.remove());
    alvosCriados = [];
  });

  it('fechado (aberto=false) não renderiza nada', () => {
    alvosCriados = criarAlvos(['um', 'dois', 'tres']);
    TestBed.configureTestingModule({ imports: [TourGuiado] });
    const fixture = TestBed.createComponent(TourGuiado);
    fixture.componentRef.setInput('passos', PASSOS);
    fixture.componentRef.setInput('aberto', false);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent.trim()).toBe('');
  });

  it('aberto, mostra o título e a descrição do passo 0', () => {
    alvosCriados = criarAlvos(['um', 'dois', 'tres']);
    const { texto } = criar();

    expect(texto()).toContain('Passo um');
    expect(texto()).toContain('Descrição do passo um');
    expect(texto()).toContain('Passo 1 de 3');
  });

  it('"Voltar" não aparece no primeiro passo', () => {
    alvosCriados = criarAlvos(['um', 'dois', 'tres']);
    const { botao } = criar();

    expect(botao('Voltar')).toBeUndefined();
  });

  it('"Próximo" avança pro passo seguinte', () => {
    alvosCriados = criarAlvos(['um', 'dois', 'tres']);
    const { fixture, botao, texto } = criar();

    botao('Próximo')?.click();
    fixture.detectChanges();

    expect(texto()).toContain('Passo dois');
    expect(texto()).toContain('Passo 2 de 3');
    expect(botao('Voltar')).toBeDefined();
  });

  it('no último passo, o botão principal vira "Concluir" e fecha o tour', () => {
    alvosCriados = criarAlvos(['um', 'dois', 'tres']);
    const { fixture, botao, fechou } = criar();

    botao('Próximo')?.click();
    fixture.detectChanges();
    botao('Próximo')?.click();
    fixture.detectChanges();

    expect(botao('Próximo')).toBeUndefined();
    const botaoConcluir = botao('Concluir');
    expect(botaoConcluir).toBeDefined();

    botaoConcluir?.click();
    fixture.detectChanges();

    expect(fechou()).toBe(true);
  });

  it('"Pular" fecha o tour de qualquer passo', () => {
    alvosCriados = criarAlvos(['um', 'dois', 'tres']);
    const { fechou, botao } = criar();

    botao('Pular')?.click();

    expect(fechou()).toBe(true);
  });

  it('Esc fecha o tour', () => {
    alvosCriados = criarAlvos(['um', 'dois', 'tres']);
    const { fixture, fechou } = criar();

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    fixture.detectChanges();

    expect(fechou()).toBe(true);
  });

  it('passo cujo alvo não existe no DOM é pulado automaticamente', () => {
    // Só "um" e "tres" existem — "dois" (índice 1) não tem alvo.
    alvosCriados = criarAlvos(['um', 'tres']);
    const { fixture, botao, texto } = criar();

    botao('Próximo')?.click();
    fixture.detectChanges();

    expect(texto()).toContain('Passo três');
  });

  it('nenhum passo com alvo válido fecha o tour sozinho', () => {
    alvosCriados = [];
    const { fechou } = criar();

    expect(fechou()).toBe(true);
  });

  it('alvo com caixa zerada (ex: host "display: contents" de um componente como app-botao) usa a caixa do primeiro filho real', () => {
    // Regressão: apontar um passo pra um componente com `:host { display:
    // contents }` (ex: `app-botao`) fazia `getBoundingClientRect()` voltar
    // tudo zerado — o destaque virava um "buraco" de tamanho zero (a tela
    // ficava uniformemente escura, sem realce nenhum) e o balão caía no
    // canto superior esquerdo por conta da matemática de posicionamento
    // partindo de left/top zero.
    const host = document.createElement('div');
    host.setAttribute('data-teste-alvo', 'zerado');
    const filho = document.createElement('button');
    filho.textContent = 'Ação';
    host.appendChild(filho);
    document.body.appendChild(host);
    alvosCriados = [host];

    const retanguloZero = { top: 0, left: 0, width: 0, height: 0, bottom: 0, right: 0, x: 0, y: 0, toJSON: () => ({}) } as DOMRect;
    const retanguloFilho = {
      top: 200,
      left: 300,
      width: 80,
      height: 32,
      bottom: 232,
      right: 380,
      x: 300,
      y: 200,
      toJSON: () => ({}),
    } as DOMRect;
    host.getBoundingClientRect = () => retanguloZero;
    filho.getBoundingClientRect = () => retanguloFilho;

    const passos: PassoTour[] = [{ alvo: '[data-teste-alvo="zerado"]', titulo: 'Zerado', descricao: 'desc' }];
    const { fixture } = criar(passos);

    const destaque = (fixture.nativeElement as HTMLElement).querySelector('.destaque') as HTMLElement;
    expect(destaque.style.left).toBe('292px');
    expect(destaque.style.top).toBe('192px');
    expect(destaque.style.width).toBe('96px');
    expect(destaque.style.height).toBe('48px');
  });

  describe('transição CSS só na troca de passo, não no acompanhamento contínuo', () => {
    // Regressão: a transição ficava ligada o tempo todo, então cada
    // recálculo de posição do loop de `requestAnimationFrame` (inclusive
    // durante uma rolagem comum, sem trocar de passo) reacionava a
    // animação — o destaque "corria atrás" do alvo em vez de ficar
    // grudado nele.
    beforeEach(() => vi.useFakeTimers());
    afterEach(() => vi.useRealTimers());

    it('logo ao abrir num alvo válido, a transição fica ligada', () => {
      alvosCriados = criarAlvos(['um', 'dois', 'tres']);
      const { destaqueEstaAnimando } = criar();

      expect(destaqueEstaAnimando()).toBe(true);
    });

    it('depois da duração da animação, a transição desliga sozinha', () => {
      alvosCriados = criarAlvos(['um', 'dois', 'tres']);
      const { fixture, destaqueEstaAnimando } = criar();

      vi.advanceTimersByTime(300);
      fixture.detectChanges();

      expect(destaqueEstaAnimando()).toBe(false);
    });
  });
});
