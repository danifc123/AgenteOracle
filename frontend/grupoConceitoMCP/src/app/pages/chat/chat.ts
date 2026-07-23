import { HttpClient } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../app-config';
import { ModuloHeader } from '../../componentes/modulo-header/modulo-header';
import { ChatEntrada } from './entrada/chat-entrada';
import { ChatMensagens, ConsultaUsada, MensagemChat } from './mensagens/chat-mensagens';

interface RespostaChat {
  resposta: string;
  consultas: ConsultaUsada[];
}

@Component({
  selector: 'app-chat',
  imports: [ChatMensagens, ChatEntrada, ModuloHeader],
  templateUrl: './chat.html',
  styleUrl: './chat.scss'
})
export class Chat {
  private readonly http = inject(HttpClient);

  mensagens = signal<MensagemChat[]>([]);
  entrada = signal('');
  enviando = signal(false);
  erro = signal<string | null>(null);
  baixandoSql = signal<string | null>(null);

  enviar(): void {
    const texto = this.entrada().trim();
    if (!texto || this.enviando()) {
      return;
    }

    const historico = this.mensagens().map(({ role, content }) => ({ role, content }));

    this.mensagens.update((atual) => [...atual, { role: 'user', content: texto }]);
    this.entrada.set('');
    this.enviando.set(true);
    this.erro.set(null);

    this.http
      .post<RespostaChat>(`${MCP_API_BASE_URL}/api/chat`, { mensagem: texto, historico })
      .subscribe({
        next: (resultado) => {
          this.mensagens.update((atual) => [
            ...atual,
            { role: 'assistant', content: resultado.resposta, consultas: resultado.consultas }
          ]);
          this.enviando.set(false);
        },
        error: () => {
          this.erro.set('Não foi possível falar com o agente. Verifique se o servidor e o Ollama estão em execução.');
          this.enviando.set(false);
        }
      });
  }

  baixarRelatorio(sql: string): void {
    if (this.baixandoSql()) {
      return;
    }

    this.baixandoSql.set(sql);
    this.erro.set(null);

    this.http
      .post(`${MCP_API_BASE_URL}/api/relatorio/exportar`, { sql }, { observe: 'response', responseType: 'blob' })
      .subscribe({
        next: (resposta) => {
          const blob = resposta.body;
          if (!blob) {
            this.baixandoSql.set(null);
            return;
          }

          const nomeArquivo = this.extrairNomeArquivo(resposta.headers.get('content-disposition'));
          const url = URL.createObjectURL(blob);
          const link = document.createElement('a');
          link.href = url;
          link.download = nomeArquivo;
          link.click();
          URL.revokeObjectURL(url);
          this.baixandoSql.set(null);
        },
        error: () => {
          this.erro.set('Não foi possível gerar o Excel do relatório.');
          this.baixandoSql.set(null);
        }
      });
  }

  private extrairNomeArquivo(contentDisposition: string | null): string {
    const match = contentDisposition?.match(/filename="?([^"]+)"?/);
    return match?.[1] ?? 'relatorio.xlsx';
  }
}
