import { Component, HostListener, input, output } from '@angular/core';

@Component({
  selector: 'app-dialog',
  imports: [],
  templateUrl: './dialog.html',
  styleUrl: './dialog.scss'
})
export class Dialog {
  aberto = input(false);
  titulo = input('');

  fechar = output<void>();

  @HostListener('document:keydown.escape')
  aoPressionarEsc(): void {
    if (this.aberto()) {
      this.fechar.emit();
    }
  }
}
