import { Component, ElementRef, HostListener, inject, model, signal } from '@angular/core';

export type ModoFiltroListaFaixa = 'lista' | 'faixa';

/** Ícone compacto que abre um popover pra trocar entre os dois modos de
 * filtro de uma coluna "texto-numerico" (ex: "nota" — lista de valores
 * exatos ou faixa numérica). Existe porque um alternador sempre visível
 * (2 botões) ao lado do campo aumentava a altura só dessa célula do grid
 * de filtros, empurrando as células vizinhas (grid `align-items: stretch`
 * por padrão) e quebrando o alinhamento da tela. Fica posicionado sozinho
 * (`:host { position: absolute }`) no canto do campo que controla, sem
 * ocupar espaço no fluxo normal — o container em volta precisa de
 * `position: relative`. Fechar ao clicar fora é o mesmo padrão de
 * `select-busca`. */
@Component({
  selector: 'app-alternador-lista-faixa',
  imports: [],
  templateUrl: './alternador-lista-faixa.html',
  styleUrl: './alternador-lista-faixa.scss',
})
export class AlternadorListaFaixa {
  private readonly elementRef = inject(ElementRef);

  modo = model<ModoFiltroListaFaixa>('lista');

  protected readonly aberto = signal(false);

  protected alternarAberto(): void {
    this.aberto.update((atual) => !atual);
  }

  protected escolher(modo: ModoFiltroListaFaixa): void {
    this.modo.set(modo);
    this.aberto.set(false);
  }

  @HostListener('document:click', ['$event'])
  protected aoClicarFora(event: MouseEvent): void {
    if (!this.elementRef.nativeElement.contains(event.target as Node)) {
      this.aberto.set(false);
    }
  }
}
