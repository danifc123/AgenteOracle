import { Component, inject, signal } from '@angular/core';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';
import { ChatFinanceiro } from '../../../../servicos/chat-financeiro/chat-financeiro';
import { ChatEntrada } from './entrada/chat-entrada';
import { ChatMensagens } from './mensagens/chat-mensagens';

/** Estado da conversa (mensagens/enviando/erros) vive em `ChatFinanceiro`
 * (serviço root), não aqui — sobrevive à navegação, então sair da tela no
 * meio de uma pergunta não perde a resposta. Esta classe só cuida do
 * rascunho ainda não enviado (`entrada`), que não faz sentido sobreviver. */
@Component({
  selector: 'app-chat',
  imports: [ChatMensagens, ChatEntrada, ModuloHeader],
  templateUrl: './chat.html',
  styleUrl: './chat.scss',
})
export class Chat {
  protected readonly servico = inject(ChatFinanceiro);

  entrada = signal('');

  enviar(): void {
    const texto = this.entrada().trim();
    if (!texto || this.servico.enviando()) {
      return;
    }
    this.servico.enviarMensagem(texto);
    this.entrada.set('');
  }

  baixarRelatorio(dados: { sql: string; titulo: string }): void {
    this.servico.baixarRelatorio(dados.sql, dados.titulo);
  }
}
