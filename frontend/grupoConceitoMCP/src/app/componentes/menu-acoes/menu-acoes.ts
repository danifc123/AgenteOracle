import { Component, DestroyRef, ElementRef, HostListener, ViewChild, inject, signal } from '@angular/core';

interface PosicaoPainel {
  top: number;
  left: number;
}

/** Menu de "mais ações" genérico (ícone de três pontos + painel flutuante)
 * — não sabe nada sobre quais ações existem, só abre/fecha/posiciona;
 * quem usa projeta o conteúdo (`<ng-content>`, normalmente uma lista de
 * `app-botao`). Mesma técnica de posicionamento de `select-busca.ts`
 * (`getBoundingClientRect` + `requestAnimationFrame` enquanto aberto,
 * fecha sozinho em scroll/resize/clique fora/Esc) — o painel abre
 * alinhado pela BORDA DIREITA do gatilho de propósito: é pensado pro
 * canto direito de uma linha de tabela, alinhar pela esquerda vazaria da
 * tela nesse caso. Fecha sozinho depois de qualquer clique dentro do
 * painel — um item de menu não precisa saber que está dentro de um menu
 * pra fechá-lo ao ser clicado (o clique do próprio item já disparou antes
 * de borbulhar até aqui). */
@Component({
  selector: 'app-menu-acoes',
  imports: [],
  templateUrl: './menu-acoes.html',
  styleUrl: './menu-acoes.scss',
})
export class MenuAcoes {
  private readonly elementRef = inject(ElementRef);

  @ViewChild('gatilho') private readonly gatilhoRef!: ElementRef<HTMLButtonElement>;
  @ViewChild('painel') private readonly painelRef?: ElementRef<HTMLDivElement>;

  protected readonly aberto = signal(false);
  protected readonly posicao = signal<PosicaoPainel>({ top: 0, left: 0 });

  private idAcompanhamento: number | null = null;

  constructor() {
    // Mesmo motivo do `DestroyRef.onDestroy` em `tour-guiado.ts`: sem
    // isso, destruir o componente com o menu aberto deixaria o loop de
    // `requestAnimationFrame` rodando pra sempre.
    inject(DestroyRef).onDestroy(() => this.pararAcompanhamento());
  }

  protected toggle(): void {
    if (this.aberto()) {
      this.fechar();
      return;
    }
    this.atualizarPosicao();
    this.aberto.set(true);
    this.iniciarAcompanhamento();
  }

  @HostListener('document:click', ['$event'])
  protected aoClicarFora(event: MouseEvent): void {
    if (!this.elementRef.nativeElement.contains(event.target as Node)) {
      this.fechar();
    }
  }

  @HostListener('window:scroll')
  @HostListener('window:resize')
  protected aoRolarOuRedimensionar(): void {
    this.fechar();
  }

  @HostListener('document:keydown.escape')
  protected aoPressionarEsc(): void {
    this.fechar();
  }

  protected fecharAoClicarDentro(): void {
    this.fechar();
  }

  private fechar(): void {
    this.aberto.set(false);
    this.pararAcompanhamento();
  }

  private pararAcompanhamento(): void {
    if (this.idAcompanhamento !== null) {
      cancelAnimationFrame(this.idAcompanhamento);
      this.idAcompanhamento = null;
    }
  }

  private iniciarAcompanhamento(): void {
    const passo = (): void => {
      if (!this.aberto()) {
        this.idAcompanhamento = null;
        return;
      }
      this.atualizarPosicao();
      this.idAcompanhamento = requestAnimationFrame(passo);
    };
    this.idAcompanhamento = requestAnimationFrame(passo);
  }

  private atualizarPosicao(): void {
    const retangulo = this.gatilhoRef.nativeElement.getBoundingClientRect();
    const larguraPainel = this.painelRef?.nativeElement.offsetWidth ?? 0;
    const alturaPainel = this.painelRef?.nativeElement.offsetHeight ?? 0;
    const espacoAbaixo = window.innerHeight - retangulo.bottom;
    const abrirParaCima = alturaPainel > 0 && espacoAbaixo < alturaPainel + 4;

    this.posicao.set({
      top: abrirParaCima ? Math.max(4, retangulo.top - alturaPainel - 4) : retangulo.bottom + 4,
      left: Math.max(4, retangulo.right - larguraPainel),
    });
  }
}
