import { Component, ElementRef, effect, input, output, viewChild } from '@angular/core';
import { Botao } from '../../../componentes/botao/botao';

export interface ConsultaUsada {
  ferramenta: string;
  argumentos: Record<string, unknown>;
  linhas_retornadas?: number | null;
}

export interface MensagemChat {
  role: 'user' | 'assistant';
  content: string;
  consultas?: ConsultaUsada[];
}

@Component({
  selector: 'app-chat-mensagens',
  imports: [Botao],
  templateUrl: './chat-mensagens.html',
  styleUrl: './chat-mensagens.scss'
})
export class ChatMensagens {
  private readonly listaMensagens = viewChild<ElementRef<HTMLDivElement>>('listaMensagens');

  mensagens = input<MensagemChat[]>([]);
  enviando = input(false);
  baixandoSql = input<string | null>(null);

  baixarRelatorio = output<string>();

  constructor() {
    effect(() => {
      this.mensagens();
      this.enviando();
      queueMicrotask(() => {
        const elemento = this.listaMensagens()?.nativeElement;
        if (elemento) {
          elemento.scrollTop = elemento.scrollHeight;
        }
      });
    });
  }
}
