import { Component, input, output } from '@angular/core';
import { Botao } from '../../../componentes/botao/botao';

@Component({
  selector: 'app-chat-entrada',
  imports: [Botao],
  templateUrl: './chat-entrada.html',
  styleUrl: './chat-entrada.scss'
})
export class ChatEntrada {
  entrada = input('');
  enviando = input(false);

  entradaChange = output<string>();
  enviar = output<void>();

  aoPressionarEnter(evento: Event): void {
    const teclado = evento as KeyboardEvent;
    if (!teclado.shiftKey) {
      teclado.preventDefault();
      this.enviar.emit();
    }
  }
}
