import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { MCP_API_BASE_URL } from '../app-config';

export interface VagaCritica {
  id: number;
  titulo: string;
  localizacao: string;
  ativa: boolean;
  criado_em: string;
}

export type NivelFit = 'alto' | 'medio' | 'baixo';
export type StatusCandidato = 'pendente' | 'avancado' | 'descartado';

export interface CriterioCandidato {
  nome: string;
  nota: number;
}

export interface Candidato {
  id: number | null;
  nome: string;
  vaga_id: number;
  vaga_sugerida_id: number;
  score: number;
  melhor_score?: number;
  scores_por_vaga: Record<string, number>;
  resumo_ia: string;
  criterios: CriterioCandidato[];
  pontos_fortes: string[];
  pontos_atencao: string[];
  status: StatusCandidato;
  criado_em: string;
  salvo: boolean;
}

export interface AnaliseEmAndamento {
  id: string;
  nomeArquivo: string;
  vagaId: number;
}

export interface NotificacaoAnalise {
  id: string;
  candidatoId: number | null;
  vagaId: number;
  candidatoNome: string;
  vagaTitulo: string;
  score: number;
  salvo: boolean;
  vista: boolean;
}

export const ROTULOS_STATUS: Record<StatusCandidato, string> = {
  pendente: 'Pendente',
  avancado: 'Avançado',
  descartado: 'Descartado',
};

export const ROTULOS_FIT: Record<NivelFit, string> = {
  alto: 'Alto fit',
  medio: 'Fit médio',
  baixo: 'Baixo fit',
};

export const CORES_FIT: Record<NivelFit, string> = {
  alto: '#2f9e58',
  medio: '#e8871e',
  baixo: '#9a2f2f',
};

export function nivelFit(score: number): NivelFit {
  if (score >= 75) {
    return 'alto';
  }
  if (score >= 50) {
    return 'medio';
  }
  return 'baixo';
}

/** MÓDULO RH — ANÁLISE DE CURRÍCULO EM SEGUNDO PLANO (2026-08)
 *
 * Client HTTP do backend real (`server/rh/candidatos.py`, `server/rh/vagas.py`)
 * — vagas e candidatos agora são persistidos no Postgres (a "análise da IA"
 * em si ainda é mock no backend, ver docstring de `tools/rh/candidatos.py`;
 * o que mudou aqui é só onde o dado mora, não o quão real é o score).
 *
 * Continua sendo um serviço global (mesmo papel que `Auditoria` cumpre pro
 * sino/painel de auditoria): `iniciarAnalise` dispara o POST e NÃO espera a
 * resposta antes de devolver o controle pra tela — o componente fecha o
 * dialog na hora, e o `subscribe` só atualiza `notificacoes`/`candidatos`
 * quando o backend realmente terminar (POST fica "pendurado" por alguns
 * segundos no servidor simulando o processamento — ver
 * `server/rh/candidatos.py`). Isso preserva a experiência de "roda em
 * segundo plano" mesmo sem fila/job assíncrono de verdade.
 */
@Injectable({ providedIn: 'root' })
export class AnaliseCurriculo {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);

  /** Vaga cujos candidatos estão em `candidatos()` no momento — usado só
   * pra decidir se um candidato recém-analisado deve ser inserido direto
   * na lista já carregada ou se basta ficar salvo no banco (aparece
   * sozinho na próxima vez que essa vaga for carregada). */
  private vagaCandidatosCarregados: number | null = null;

  readonly vagas = signal<VagaCritica[]>([]);
  readonly candidatos = signal<Candidato[]>([]);
  readonly emAndamento = signal<AnaliseEmAndamento[]>([]);
  readonly notificacoes = signal<NotificacaoAnalise[]>([]);
  /** Setado por `abrirResultado` (só depois que o candidato é buscado do
   * backend de novo — pode ter vindo de outra tela, sem os candidatos
   * dessa vaga carregados) — a tela `/rh` observa isso pra abrir o
   * candidato certo automaticamente quando o usuário clica "Ver resultado"
   * vindo de qualquer outra tela do sistema. */
  readonly candidatoParaAbrir = signal<Candidato | null>(null);

  readonly notificacoesNaoVistas = computed(() => this.notificacoes().filter((notificacao) => !notificacao.vista));

  constructor() {
    this.carregarVagas();
  }

  abrirResultado(notificacaoId: string): void {
    const notificacao = this.notificacoes().find((item) => item.id === notificacaoId);
    if (!notificacao || notificacao.candidatoId === null) {
      return;
    }
    this.marcarComoVista(notificacaoId);
    this.router.navigateByUrl('/rh');

    this.vagaCandidatosCarregados = notificacao.vagaId;
    this.http
      .get<Candidato[]>(`${MCP_API_BASE_URL}/api/rh/candidatos`, { params: { vaga_id: notificacao.vagaId } })
      .subscribe({
        next: (candidatos) => {
          this.candidatos.set(candidatos);
          this.candidatoParaAbrir.set(candidatos.find((item) => item.id === notificacao.candidatoId) ?? null);
        },
      });
  }

  atualizarStatusCandidato(id: number, status: StatusCandidato): void {
    this.http.patch<Candidato>(`${MCP_API_BASE_URL}/api/rh/candidatos/${id}`, { status }).subscribe({
      next: (atualizado) => {
        this.candidatos.update((atual) => atual.map((candidato) => (candidato.id === id ? atualizado : candidato)));
      },
    });
  }

  carregarCandidatos(vagaId: number): void {
    this.vagaCandidatosCarregados = vagaId;
    this.http
      .get<Candidato[]>(`${MCP_API_BASE_URL}/api/rh/candidatos`, { params: { vaga_id: vagaId } })
      .subscribe({
        next: (candidatos) => this.candidatos.set(candidatos),
        error: () => this.candidatos.set([]),
      });
  }

  carregarVagas(): void {
    this.http.get<VagaCritica[]>(`${MCP_API_BASE_URL}/api/rh/vagas`).subscribe({
      next: (vagas) => this.vagas.set(vagas),
      error: () => this.vagas.set([]),
    });
  }

  iniciarAnalise(arquivo: File, vagaId: number): void {
    const id = `analise-${Date.now()}-${Math.round(Math.random() * 1000)}`;
    this.emAndamento.update((atual) => [...atual, { id, nomeArquivo: arquivo.name, vagaId }]);

    const formData = new FormData();
    formData.append('arquivo', arquivo);
    formData.append('vaga_id', String(vagaId));

    this.http.post<Candidato>(`${MCP_API_BASE_URL}/api/rh/candidatos/analisar`, formData).subscribe({
      next: (candidato) => this.concluirAnalise(id, candidato),
      error: () => this.emAndamento.update((atual) => atual.filter((item) => item.id !== id)),
    });
  }

  limparCandidatoParaAbrir(): void {
    this.candidatoParaAbrir.set(null);
  }

  /** Vagas mais o `titulo` de `vagaId`, pronto pra exibição — usado pelas
   * telas que só precisam do nome (ex: coluna "vaga sugerida"). */
  tituloVaga(vagaId: number): string {
    return this.vagas().find((item) => item.id === vagaId)?.titulo ?? '';
  }

  marcarComoVista(notificacaoId: string): void {
    this.notificacoes.update((atual) =>
      atual.map((item) => (item.id === notificacaoId ? { ...item, vista: true } : item)),
    );
  }

  private concluirAnalise(analiseId: string, candidato: Candidato): void {
    this.emAndamento.update((atual) => atual.filter((item) => item.id !== analiseId));

    if (candidato.salvo && candidato.vaga_id === this.vagaCandidatosCarregados) {
      this.candidatos.update((atual) => [...atual, candidato]);
    }

    const vaga = this.vagas().find((item) => item.id === candidato.vaga_id);
    this.notificacoes.update((atual) => [
      ...atual,
      {
        id: `notif-${candidato.id ?? analiseId}`,
        candidatoId: candidato.id,
        vagaId: candidato.vaga_id,
        candidatoNome: candidato.nome,
        vagaTitulo: vaga?.titulo ?? '',
        score: candidato.score,
        salvo: candidato.salvo,
        vista: false,
      },
    ]);
  }
}
