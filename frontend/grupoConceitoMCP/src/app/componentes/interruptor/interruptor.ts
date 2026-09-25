import { Component, input, output } from '@angular/core';

let proximoId = 0;

/** Interruptor (switch) com rótulo e descrição; o estado é controlado por quem usa. */
@Component({
  selector: 'app-interruptor',
  imports: [],
  templateUrl: './interruptor.html',
  styleUrl: './interruptor.scss',
})
export class Interruptor {
  rotulo = input.required<string>();
  descricao = input('');
  marcado = input(false);
  desabilitado = input(false);

  alterado = output<boolean>();

  protected readonly id = `interruptor-${proximoId++}`;

  protected alternar(): void {
    if (!this.desabilitado()) {
      this.alterado.emit(!this.marcado());
    }
  }
}
