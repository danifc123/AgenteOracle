import { Component, ElementRef, HostListener, inject, signal } from '@angular/core';

@Component({
  selector: 'app-menu-opcoes',
  imports: [],
  templateUrl: './menu-opcoes.html',
  styleUrl: './menu-opcoes.scss'
})
export class MenuOpcoes {
  private readonly elementRef = inject(ElementRef);

  protected readonly aberto = signal(false);

  toggle(): void {
    this.aberto.update((valor) => !valor);
  }

  fechar(): void {
    this.aberto.set(false);
  }

  @HostListener('document:click', ['$event'])
  aoClicarFora(event: MouseEvent): void {
    if (!this.elementRef.nativeElement.contains(event.target as Node)) {
      this.aberto.set(false);
    }
  }
}
