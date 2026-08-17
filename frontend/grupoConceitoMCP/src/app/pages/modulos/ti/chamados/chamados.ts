import { DatePipe } from '@angular/common';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../../../app-config';
import { Botao } from '../../../../componentes/botao/botao';
import { Dialog } from '../../../../componentes/dialog/dialog';
import { EstadoVazio } from '../../../../componentes/estado-vazio/estado-vazio';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';
import { mensagemErro } from '../../../../servicos/mensagens-erro';

export type StatusChamado = 'novo' | 'aguardando_usuario' | 'fila_atendimento';

export interface Chamado {
  id: number;
  titulo: string;
  descricao: string;
  categoria: string;
  status: StatusChamado;
  solicitante: string;
  email: string;
  avaliacao_mensagem: string | null;
  reportado_em: string | null;
  criado_em: string;
}

const ROTULOS_STATUS: Record<StatusChamado, string> = {
  novo: 'Novo',
  aguardando_usuario: 'Aguardando você',
  fila_atendimento: 'Na fila',
};

/** MÓDULO TI — TELA "CENTRAL DE CHAMADOS" (2026-08)
 *
 * Prova de conceito do item "Service Desk IA" da planilha de demandas —
 * hoje roda sobre dado mockado (`tools/ti/glpi.py::ClienteGLPIMock`,
 * nenhuma conexão real com o GLPI ainda), pra você mostrar a ideia pros
 * colegas antes de investir na integração de verdade. "Verificar Chamados
 * Novos" chama `POST /api/ti/chamados/verificar`: a IA julga se cada
 * chamado `novo` tem informação suficiente — se não tem, ele fica
 * "Aguardando você" com a pergunta da IA em vez de ir pra fila.
 *
 * "Reportar ao usuário" (no detalhe de um chamado aguardando) simula o
 * aviso que, na integração real, sairia como e-mail — hoje só marca
 * `reportado_em` e mostra na tela o que teria sido enviado (nenhum
 * e-mail sai de verdade). Não existe, nesta versão mock, um jeito do
 * chamado voltar sozinho pra fila — na integração real isso dependeria
 * de consultar a API do GLPI de novo (polling) pra perceber que o
 * usuário completou o chamado por lá. */
@Component({
  selector: 'app-chamados-ti',
  imports: [Botao, DatePipe, Dialog, EstadoVazio, ModuloHeader],
  templateUrl: './chamados.html',
  styleUrl: './chamados.scss',
})
export class ChamadosTi {
  private readonly http = inject(HttpClient);

  protected readonly chamados = signal<Chamado[]>([]);
  protected readonly carregando = signal(true);
  protected readonly verificando = signal(false);
  protected readonly reportando = signal(false);
  protected readonly erro = signal<string | null>(null);
  protected readonly chamadoAberto = signal<Chamado | null>(null);

  constructor() {
    this.carregarChamados();
  }

  protected abrirDetalhe(chamado: Chamado): void {
    this.chamadoAberto.set(chamado);
  }

  private carregarChamados(): void {
    this.carregando.set(true);
    this.http.get<Chamado[]>(`${MCP_API_BASE_URL}/api/ti/chamados`).subscribe({
      next: (chamados) => {
        this.chamados.set(chamados);
        this.carregando.set(false);
      },
      error: () => this.carregando.set(false),
    });
  }

  protected fecharDetalhe(): void {
    this.chamadoAberto.set(null);
  }

  protected reportar(chamado: Chamado): void {
    if (this.reportando()) {
      return;
    }

    this.reportando.set(true);
    this.erro.set(null);

    this.http.post<Chamado>(`${MCP_API_BASE_URL}/api/ti/chamados/${chamado.id}/reportar`, {}).subscribe({
      next: (atualizado) => {
        this.chamados.update((atual) => atual.map((item) => (item.id === atualizado.id ? atualizado : item)));
        this.chamadoAberto.set(atualizado);
        this.reportando.set(false);
      },
      error: (erro: HttpErrorResponse) => {
        this.erro.set(mensagemErro(erro, 'Não foi possível reportar ao usuário.'));
        this.reportando.set(false);
      },
    });
  }

  protected rotuloStatus(status: StatusChamado): string {
    return ROTULOS_STATUS[status];
  }

  protected verificarChamadosNovos(): void {
    if (this.verificando()) {
      return;
    }

    this.verificando.set(true);
    this.erro.set(null);

    this.http.post<Chamado[]>(`${MCP_API_BASE_URL}/api/ti/chamados/verificar`, {}).subscribe({
      next: (chamados) => {
        this.chamados.set(chamados);
        this.verificando.set(false);
      },
      error: (erro: HttpErrorResponse) => {
        this.erro.set(mensagemErro(erro, 'Não foi possível verificar os chamados.'));
        this.verificando.set(false);
      },
    });
  }
}
