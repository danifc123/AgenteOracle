import { HttpClient } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../../app-config';
import { TabelaTransacoes, Transacao } from '../../../componentes/tabela-transacoes/tabela-transacoes';

@Component({
  selector: 'app-transacoes',
  imports: [TabelaTransacoes],
  templateUrl: './transacoes.html',
  styleUrl: './transacoes.scss'
})
export class Transacoes {
  private readonly http = inject(HttpClient);

  transacoes: Transacao[] = [];
  carregando = signal(true);
  erroCarregamento = signal<string | null>(null);
  exportando = signal(false);
  erroExportacao = signal<string | null>(null);

  constructor() {
    this.carregarTransacoes();
  }

  carregarTransacoes(): void {
    this.carregando.set(true);
    this.erroCarregamento.set(null);

    this.http.get<Transacao[]>(`${MCP_API_BASE_URL}/api/transacoes`).subscribe({
      next: (transacoes) => {
        this.transacoes = transacoes;
        this.carregando.set(false);
      },
      error: () => {
        this.erroCarregamento.set('Não foi possível carregar as transações. Verifique se o servidor está em execução.');
        this.carregando.set(false);
      }
    });
  }

  exportarRelatorio(): void {
    this.exportando.set(true);
    this.erroExportacao.set(null);

    this.http
      .get(`${MCP_API_BASE_URL}/api/transacoes/exportar`, {
        observe: 'response',
        responseType: 'blob'
      })
      .subscribe({
        next: (resposta) => {
          const blob = resposta.body;
          if (!blob) {
            return;
          }

          const nomeArquivo = this.extrairNomeArquivo(resposta.headers.get('content-disposition'));
          const url = URL.createObjectURL(blob);
          const link = document.createElement('a');
          link.href = url;
          link.download = nomeArquivo;
          link.click();
          URL.revokeObjectURL(url);
          this.exportando.set(false);
        },
        error: () => {
          this.erroExportacao.set('Não foi possível gerar o relatório. Verifique se o servidor está em execução.');
          this.exportando.set(false);
        }
      });
  }

  private extrairNomeArquivo(contentDisposition: string | null): string {
    const match = contentDisposition?.match(/filename="?([^"]+)"?/);
    return match?.[1] ?? 'transacoes_financeiras.csv';
  }
}
