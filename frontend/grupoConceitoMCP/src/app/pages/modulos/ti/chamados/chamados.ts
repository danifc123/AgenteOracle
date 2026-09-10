import { DatePipe } from '@angular/common';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
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

/** MÓDULO TI — TELA "AUDITORIA DE CHAMADOS" (2026-08)
 *
 * Item "Service Desk IA" da planilha de demandas — integração real com o
 * GLPI (`tools/ti/glpi.py::ClienteGLPIReal`), sem cliente mock. A
 * verificação de chamado `novo` não depende mais de clique manual: um
 * poller em background no próprio servidor (`server/ti/chamados.py::
 * iniciar_poller_verificar_chamados`) roda sozinho a cada poucos
 * minutos. Chamado `aguardando_usuario` (aparece na tela, mas não é
 * reavaliado pelo poller de propósito — gastaria IA à toa a cada rodada
 * sem que o solicitante tenha respondido nada) só volta a ser avaliado
 * via o botão "Verificar" por linha, ou quando o GLPI resolver sozinho
 * depois de 3 dias sem resposta.
 *
 * "Reportar ao usuário" (no detalhe de um chamado aguardando) só marca
 * `reportado_em` e mostra na tela o que teria sido enviado — nenhum
 * e-mail sai de verdade ainda, mesmo com o GLPI real (ver docstring de
 * `tools/ti/glpi.py::ClienteGLPIReal.reportar_usuario`). A tela em si só
 * carrega a lista uma vez, ao abrir — não se atualiza sozinha enquanto o
 * poller processa em background; recarregar a página mostra o estado
 * mais recente. */
@Component({
  selector: 'app-chamados-ti',
  imports: [Botao, DatePipe, Dialog, EstadoVazio, ModuloHeader],
  templateUrl: './chamados.html',
  styleUrl: './chamados.scss',
})
export class ChamadosTi {
  private readonly http = inject(HttpClient);
  private readonly configuracoesTi = inject(ConfiguracoesTi);
  private readonly ITENS_POR_PAGINA = 10;

  protected readonly chamados = signal<Chamado[]>([]);
  protected readonly carregando = signal(true);
  // id do chamado sendo verificado individualmente — só aquele botão da
  // linha mostra loading, o resto da tabela continua clicável.
  protected readonly verificandoId = signal<number | null>(null);
  protected readonly reportando = signal(false);
  protected readonly erro = signal<string | null>(null);
  protected readonly chamadoAberto = signal<Chamado | null>(null);
  protected readonly usarIa = this.configuracoesTi.usarIaAvaliacaoChamado;

  protected readonly paginaAtual = signal(1);
  protected readonly totalPaginas = computed(() =>
    Math.max(1, Math.ceil(this.chamados().length / this.ITENS_POR_PAGINA)),
  );
  protected readonly chamadosDaPagina = computed(() => {
    const inicio = (this.paginaAtual() - 1) * this.ITENS_POR_PAGINA;
    return this.chamados().slice(inicio, inicio + this.ITENS_POR_PAGINA);
  });

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
        this.paginaAtual.set(1);
        this.carregando.set(false);
      },
      error: () => this.carregando.set(false),
    });
  }

  protected paginaAnterior(): void {
    this.paginaAtual.update((atual) => Math.max(1, atual - 1));
  }

  protected proximaPagina(): void {
    this.paginaAtual.update((atual) => Math.min(this.totalPaginas(), atual + 1));
  }

  // Chamado removido da lista (foi pra fila) pode esvaziar a última
  // página — sem isso, ficaria preso numa página vazia até recarregar.
  private ajustarPaginaAtual(): void {
    if (this.paginaAtual() > this.totalPaginas()) {
      this.paginaAtual.set(this.totalPaginas());
    }
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
          this.ajustarPaginaAtual();
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
}
