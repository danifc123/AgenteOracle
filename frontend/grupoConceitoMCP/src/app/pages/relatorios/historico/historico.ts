import { DatePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../../app-config';
import { Botao } from '../../../componentes/botao/botao';
import { Dialog } from '../../../componentes/dialog/dialog';
import { ModuloHeader } from '../../../componentes/modulo-header/modulo-header';
import { formatarSql } from '../../../servicos/formatar-sql';

export interface RelatorioHistorico {
  id: string;
  titulo: string;
  sql: string;
  colunas: string[];
  total_linhas: number;
  criado_em: string;
  fixado: boolean;
  expira_em: string | null;
}

@Component({
  selector: 'app-historico',
  imports: [DatePipe, Botao, Dialog, ModuloHeader],
  templateUrl: './historico.html',
  styleUrl: './historico.scss'
})
export class Historico {
  private readonly http = inject(HttpClient);

  relatorios = signal<RelatorioHistorico[]>([]);
  carregando = signal(true);
  erro = signal<string | null>(null);
  baixandoId = signal<string | null>(null);
  apagandoId = signal<string | null>(null);
  fixandoId = signal<string | null>(null);

  relatorioSelecionado = signal<RelatorioHistorico | null>(null);
  copiado = signal(false);

  sqlFormatado = computed(() => {
    const relatorio = this.relatorioSelecionado();
    return relatorio ? formatarSql(relatorio.sql) : '';
  });

  constructor() {
    this.carregarHistorico();
  }

  carregarHistorico(): void {
    this.carregando.set(true);
    this.erro.set(null);

    this.http.get<RelatorioHistorico[]>(`${MCP_API_BASE_URL}/api/relatorios/historico`).subscribe({
      next: (relatorios) => {
        this.relatorios.set(relatorios);
        this.carregando.set(false);
      },
      error: () => {
        this.erro.set('Não foi possível carregar o histórico. Verifique se o servidor está em execução.');
        this.carregando.set(false);
      }
    });
  }

  baixarRelatorio(relatorio: RelatorioHistorico): void {
    if (this.baixandoId()) {
      return;
    }

    this.baixandoId.set(relatorio.id);
    this.erro.set(null);

    this.http
      .get(`${MCP_API_BASE_URL}/api/relatorios/historico/${relatorio.id}/exportar`, {
        observe: 'response',
        responseType: 'blob'
      })
      .subscribe({
        next: (resposta) => {
          const blob = resposta.body;
          if (!blob) {
            this.baixandoId.set(null);
            return;
          }

          const url = URL.createObjectURL(blob);
          const link = document.createElement('a');
          link.href = url;
          link.download = `${relatorio.titulo || 'relatorio'}.xlsx`;
          link.click();
          URL.revokeObjectURL(url);
          this.baixandoId.set(null);
        },
        error: () => {
          this.erro.set('Não foi possível baixar o relatório.');
          this.baixandoId.set(null);
        }
      });
  }

  apagarRelatorio(relatorio: RelatorioHistorico): void {
    if (this.apagandoId()) {
      return;
    }

    this.apagandoId.set(relatorio.id);
    this.erro.set(null);

    this.http.delete(`${MCP_API_BASE_URL}/api/relatorios/historico/${relatorio.id}`).subscribe({
      next: () => {
        this.relatorios.update((atual) => atual.filter((item) => item.id !== relatorio.id));
        this.apagandoId.set(null);
      },
      error: () => {
        this.erro.set('Não foi possível apagar o relatório.');
        this.apagandoId.set(null);
      }
    });
  }

  verConsulta(relatorio: RelatorioHistorico): void {
    this.copiado.set(false);
    this.relatorioSelecionado.set(relatorio);
  }

  fecharConsulta(): void {
    this.relatorioSelecionado.set(null);
  }

  copiarConsulta(): void {
    const sql = this.sqlFormatado();
    if (!sql) {
      return;
    }

    navigator.clipboard.writeText(sql).then(() => {
      this.copiado.set(true);
      setTimeout(() => this.copiado.set(false), 2000);
    });
  }

  alternarFixado(relatorio: RelatorioHistorico): void {
    if (this.fixandoId()) {
      return;
    }

    const novoFixado = !relatorio.fixado;
    this.fixandoId.set(relatorio.id);
    this.erro.set(null);

    this.http
      .patch<{ ok: boolean }>(`${MCP_API_BASE_URL}/api/relatorios/historico/${relatorio.id}`, { fixado: novoFixado })
      .subscribe({
        next: () => {
          this.fixandoId.set(null);
          this.carregarHistorico();
        },
        error: () => {
          this.erro.set('Não foi possível fixar/desfixar o relatório.');
          this.fixandoId.set(null);
        }
      });
  }
}
