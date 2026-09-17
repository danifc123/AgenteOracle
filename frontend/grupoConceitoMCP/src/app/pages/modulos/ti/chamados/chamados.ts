import { DatePipe } from '@angular/common';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../../../app-config';
import { Botao } from '../../../../componentes/botao/botao';
import { ConteudoChamado } from '../../../../componentes/conteudo-chamado/conteudo-chamado';
import { Dialog } from '../../../../componentes/dialog/dialog';
import { EstadoVazio } from '../../../../componentes/estado-vazio/estado-vazio';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';
import { SaudeArea, SaudeRoster } from '../../../../componentes/saude-roster/saude-roster';
import { ConfiguracoesTi } from '../../../../servicos/configuracoes-ti';
import { mensagemErro } from '../../../../servicos/mensagens-erro';
import { Sessao } from '../../../../servicos/sessao';

export type StatusChamado = 'novo' | 'aguardando_usuario' | 'fila_atendimento';

export interface Chamado {
  id: number;
  titulo: string;
  descricao: string;
  categoria: string;
  status: StatusChamado;
  solicitante: string;
  avaliacao_mensagem: string | null;
  criado_em: string;
  tecnico_atribuido: string | null;
}

interface TecnicoNome {
  identificador: string;
  nome: string;
}

/** MÓDULO TI — TELA "AUDITORIA DE CHAMADOS" (2026-08)
 *
 * Item "Service Desk IA" da planilha de demandas — integração real com o
 * GLPI (`tools/ti/glpi.py::ClienteGLPIReal`), sem cliente mock. Um poller
 * em background no próprio servidor (`server/ti/chamados.py::
 * iniciar_poller_verificar_chamados`) roda sozinho a cada poucos minutos,
 * em duas pernas: chamado `novo` é sempre avaliado; chamado
 * `aguardando_usuario` só é reavaliado quando o poller detecta uma
 * resposta nova do solicitante (não gasta IA à toa num chamado parado).
 * Se a IA insistir que falta informação numa 2ª avaliação seguida, o
 * chamado é escalado pra um técnico humano (`tecnicoEscalado()` mostra
 * isso na tela — "Aguardando resposta" vira "Com {técnico}"). O botão
 * "Verificar" por linha força uma reavaliação na hora, sem esperar o
 * poller.
 *
 * Sem botão de "reportar ao usuário" de propósito: o Followup que a IA
 * posta ao marcar `aguardando_usuario` já dispara a notificação nativa
 * do GLPI pro solicitante (mecanismo padrão dele pra mensagem em
 * chamado) — nenhum aviso extra é necessário da nossa parte. A tela em
 * si só carrega a lista uma vez, ao abrir — não se atualiza sozinha
 * enquanto o poller processa em background; recarregar a página mostra
 * o estado mais recente. */
@Component({
  selector: 'app-chamados-ti',
  imports: [Botao, ConteudoChamado, DatePipe, Dialog, EstadoVazio, ModuloHeader, SaudeRoster],
  templateUrl: './chamados.html',
  styleUrl: './chamados.scss',
})
export class ChamadosTi {
  private readonly http = inject(HttpClient);
  private readonly configuracoesTi = inject(ConfiguracoesTi);
  protected readonly sessao = inject(Sessao);
  private readonly ITENS_POR_PAGINA = 10;

  // Painel de diagnóstico só-desenvolvedor (`/api/ti/tecnicos/saude`,
  // restrito a `exigir_desenvolvedor` no backend) — mostra técnico
  // cadastrado por área, pra pegar área com zero técnicos (causa real de um
  // 500 em `escolher_tecnico`, `tools/ti/tecnicos.py`) antes de alguém
  // tropeçar nisso usando a tela de verdade.
  protected readonly saudeAreas = signal<SaudeArea[]>([]);

  protected readonly chamados = signal<Chamado[]>([]);
  protected readonly carregando = signal(true);
  // id do chamado sendo verificado individualmente — só aquele botão da
  // linha mostra loading, o resto da tabela continua clicável.
  protected readonly verificandoId = signal<number | null>(null);
  protected readonly erro = signal<string | null>(null);
  protected readonly chamadoAberto = signal<Chamado | null>(null);
  protected readonly usarIa = this.configuracoesTi.usarIaAvaliacaoChamado;
  // Nome pro badge "Com {técnico}" — vem do roster de verdade
  // (`/api/ti/tecnicos`, backend por `tools/ti/tecnicos.py`), não mais
  // fixo aqui — um técnico novo cadastrado aparece certo sem precisar
  // editar o frontend.
  private readonly nomesTecnicos = signal<Record<string, string>>({});

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
    this.carregarTecnicos();
    this.configuracoesTi.carregar();
    if (this.sessao.ehDesenvolvedor()) {
      this.carregarSaudeAreas();
    }
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

  // `null` = ainda só com a IA (aguardando resposta do solicitante); um
  // nome = já escalado pra esse técnico.
  protected tecnicoEscalado(chamado: Chamado): string | null {
    return chamado.tecnico_atribuido ? (this.nomesTecnicos()[chamado.tecnico_atribuido] ?? null) : null;
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

  private carregarTecnicos(): void {
    this.http.get<TecnicoNome[]>(`${MCP_API_BASE_URL}/api/ti/tecnicos`).subscribe({
      next: (tecnicos) => {
        this.nomesTecnicos.set(
          Object.fromEntries(tecnicos.map((tecnico) => [tecnico.identificador, tecnico.nome])),
        );
      },
      error: () => this.nomesTecnicos.set({}),
    });
  }

  private carregarSaudeAreas(): void {
    this.http.get<SaudeArea[]>(`${MCP_API_BASE_URL}/api/ti/tecnicos/saude`).subscribe({
      next: (areas) => this.saudeAreas.set(areas),
      error: () => this.saudeAreas.set([]),
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
