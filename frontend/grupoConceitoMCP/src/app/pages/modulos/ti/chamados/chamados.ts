import { DatePipe } from '@angular/common';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../../../app-config';
import { Botao } from '../../../../componentes/botao/botao';
import { Dialog } from '../../../../componentes/dialog/dialog';
import { EstadoVazio } from '../../../../componentes/estado-vazio/estado-vazio';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';
import { ConfiguracoesTi } from '../../../../servicos/configuracoes-ti';
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
  // Quem vê essa tela é sempre o time de TI acompanhando, nunca o
  // solicitante — "aguardando você" lido pela TI parece cobrar uma ação
  // dela mesma, quando quem precisa responder é o solicitante no GLPI.
  aguardando_usuario: 'Aguardando solicitante',
  fila_atendimento: 'Na fila',
};

/** MÓDULO TI — TELA "AUDITORIA DE CHAMADOS" (2026-08)
 *
 * Item "Service Desk IA" da planilha de demandas — integração real com o
 * GLPI (`tools/ti/glpi.py::ClienteGLPIReal`), sem cliente mock. "Verificar
 * Chamados Novos" chama `POST /api/ti/chamados/verificar`: a IA julga se
 * cada chamado `novo` tem informação suficiente e se a categoria escolhida
 * bate com o conteúdo (contra as ~211 categorias reais do GLPI) — se não
 * tem informação suficiente, o chamado fica "Aguardando solicitante" com a
 * pergunta da IA em vez de ir pra fila.
 *
 * "Reportar ao usuário" (no detalhe de um chamado aguardando) só marca
 * `reportado_em` e mostra na tela o que teria sido enviado — nenhum
 * e-mail sai de verdade ainda, mesmo com o GLPI real (ver docstring de
 * `tools/ti/glpi.py::ClienteGLPIReal.reportar_usuario`). O chamado
 * também não volta sozinho pra fila quando o usuário completa lá no
 * GLPI: `/verificar` só reavalia chamado com status `novo`, e o webhook só
 * dispara no evento "Ticket created" — gap conhecido, fora do escopo desta
 * rodada de integração. */
@Component({
  selector: 'app-chamados-ti',
  imports: [Botao, DatePipe, Dialog, EstadoVazio, ModuloHeader],
  templateUrl: './chamados.html',
  styleUrl: './chamados.scss',
})
export class ChamadosTi {
  private readonly http = inject(HttpClient);
  private readonly configuracoesTi = inject(ConfiguracoesTi);

  protected readonly chamados = signal<Chamado[]>([]);
  protected readonly carregando = signal(true);
  protected readonly verificando = signal(false);
  // id do chamado sendo verificado individualmente — só aquele botão da
  // linha mostra loading, o resto da tabela continua clicável.
  protected readonly verificandoId = signal<number | null>(null);
  protected readonly reportando = signal(false);
  protected readonly erro = signal<string | null>(null);
  protected readonly chamadoAberto = signal<Chamado | null>(null);
  protected readonly usarIa = this.configuracoesTi.usarIaAvaliacaoChamado;

  constructor() {
    this.carregarChamados();
    this.configuracoesTi.carregar();
  }

  protected alternarUsarIa(): void {
    const novoValor = !this.usarIa();
    this.configuracoesTi.usarIaAvaliacaoChamado.set(novoValor);
    this.configuracoesTi.definirUsarIa(novoValor).subscribe({
      error: () => this.configuracoesTi.usarIaAvaliacaoChamado.set(!novoValor),
    });
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

  protected verificarChamado(chamado: Chamado): void {
    if (this.verificandoId() !== null) {
      return;
    }

    this.verificandoId.set(chamado.id);
    this.erro.set(null);

    this.http.post<Chamado>(`${MCP_API_BASE_URL}/api/ti/chamados/${chamado.id}/verificar`, {}).subscribe({
      next: (atualizado) => {
        // "fila_atendimento" já foi entregue ao GLPI — some da lista, mesmo
        // critério de `_precisa_atencao` no backend.
        if (atualizado.status === 'fila_atendimento') {
          this.chamados.update((atual) => atual.filter((item) => item.id !== atualizado.id));
        } else {
          this.chamados.update((atual) => atual.map((item) => (item.id === atualizado.id ? atualizado : item)));
        }
        if (this.chamadoAberto()?.id === atualizado.id) {
          this.chamadoAberto.set(atualizado.status === 'fila_atendimento' ? null : atualizado);
        }
        this.verificandoId.set(null);
      },
      error: (erro: HttpErrorResponse) => {
        this.erro.set(mensagemErro(erro, 'Não foi possível verificar este chamado.'));
        this.verificandoId.set(null);
      },
    });
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
