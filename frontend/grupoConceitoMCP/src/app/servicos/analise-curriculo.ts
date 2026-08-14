import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { MCP_API_BASE_URL } from '../app-config';
import { baixarBlob, extrairNomeArquivo } from './download-arquivo';
import { mensagemErro } from './mensagens-erro';

export type StatusCandidato = 'ativo' | 'contratado' | 'descartado';

export type NivelSenioridade = 'estagiario' | 'junior' | 'pleno' | 'senior' | 'especialista' | 'nao_identificado';
export type StatusFormacao = 'concluido' | 'cursando' | 'nao_identificado';

export interface HabilidadesTecnicas {
  linguagens: string[];
  frameworks_bibliotecas: string[];
  bancos_de_dados: string[];
  ferramentas_plataformas: string[];
  metodologias: string[];
}

export interface ExperienciaProfissional {
  empresa: string;
  cargo: string;
  data_inicio: string | null;
  data_fim: string | null;
  principais_responsabilidades: string[];
  tecnologias_utilizadas: string[];
}

export interface FormacaoAcademica {
  curso: string;
  instituicao: string;
  status: StatusFormacao;
}

/** Campos granulares extraídos do currículo pela IA — ver
 * `agent/rh/perfil_candidato.py`. Candidato cadastrado antes dessa extração
 * existir fica com um objeto vazio (`{}` no banco), então todo consumo
 * daqui trata os campos como possivelmente ausentes, nunca assume presença. */
export interface PerfilEstruturado {
  nivel_senioridade?: NivelSenioridade;
  anos_experiencia_total?: number | null;
  area_atuacao_principal?: string;
  areas_atuacao_secundarias?: string[];
  habilidades_tecnicas?: HabilidadesTecnicas;
  experiencias_profissionais?: ExperienciaProfissional[];
  formacao_academica?: FormacaoAcademica[];
  certificacoes?: string[];
  idiomas?: string[];
}

export interface Candidato {
  id: number;
  nome: string;
  resumo_perfil: string;
  perfil_estruturado: PerfilEstruturado;
  status: StatusCandidato;
  criado_em: string;
}

export const ROTULOS_SENIORIDADE: Record<NivelSenioridade, string> = {
  estagiario: 'Estagiário',
  junior: 'Júnior',
  pleno: 'Pleno',
  senior: 'Sênior',
  especialista: 'Especialista',
  nao_identificado: 'Não identificado',
};

export const ROTULOS_STATUS_FORMACAO: Record<StatusFormacao, string> = {
  concluido: 'Concluído',
  cursando: 'Cursando',
  nao_identificado: 'Não identificado',
};

export interface AnaliseEmAndamento {
  id: string;
  nomeArquivo: string;
}

export interface NotificacaoAnalise {
  id: string;
  candidatoId: number;
  candidatoNome: string;
  vista: boolean;
}

/** Análise que não chegou a terminar — IA (Ollama) fora do ar, currículo
 * ilegível, etc. Separado de `NotificacaoAnalise` porque não existe
 * candidato nenhum envolvido — só uma mensagem de erro pra mostrar. */
export interface ErroAnalise {
  id: string;
  mensagem: string;
  vista: boolean;
}

export const ROTULOS_STATUS: Record<StatusCandidato, string> = {
  ativo: 'Ativo',
  contratado: 'Contratado',
  descartado: 'Descartado',
};

/** MÓDULO RH — ANÁLISE DE CURRÍCULO EM SEGUNDO PLANO (2026-08)
 *
 * Client HTTP do backend real (`server/rh/candidatos.py`) — todo currículo
 * analisado com sucesso vira candidato no pool (Postgres), com um resumo
 * de perfil escrito pela IA (Ollama, `agent/rh/perfil_candidato.py`) e um
 * embedding desse resumo (usado depois pra busca, ver
 * `servicos/busca-candidatos.ts`). Não existe mais o conceito de "vaga
 * cadastrada" nem de nota mínima pra ser salvo — todo candidato analisado
 * entra no pool; a compatibilidade com uma vaga específica é calculada sob
 * demanda, na hora da busca, não no momento do cadastro.
 *
 * Serviço global (mesmo papel que `Auditoria` cumpre pro sino/painel de
 * auditoria): `iniciarAnalise` dispara o POST e NÃO espera a resposta
 * antes de devolver o controle pra tela — o componente fecha o dialog na
 * hora, e o `subscribe` só atualiza `notificacoes`/`erros`/`candidatos`
 * quando o backend realmente terminar (a chamada de IA real — perfil +
 * embedding — é o que leva alguns segundos). Cada arquivo de uma seleção
 * múltipla vira uma chamada independente (`iniciarAnalise` uma vez por
 * arquivo), então currículos de um mesmo lote podem terminar em momentos
 * diferentes, cada um com seu próprio toast.
 */
@Injectable({ providedIn: 'root' })
export class AnaliseCurriculo {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);

  readonly candidatos = signal<Candidato[]>([]);
  readonly emAndamento = signal<AnaliseEmAndamento[]>([]);
  readonly notificacoes = signal<NotificacaoAnalise[]>([]);
  readonly erros = signal<ErroAnalise[]>([]);

  readonly notificacoesNaoVistas = computed(() => this.notificacoes().filter((notificacao) => !notificacao.vista));
  readonly errosNaoVistos = computed(() => this.erros().filter((erro) => !erro.vista));

  abrirResultado(notificacaoId: string): void {
    this.marcarComoVista(notificacaoId);
    this.router.navigateByUrl('/rh/analise-candidato');
  }

  atualizarStatusCandidato(id: number, status: StatusCandidato): void {
    this.http.patch<Candidato>(`${MCP_API_BASE_URL}/api/rh/candidatos/${id}`, { status }).subscribe({
      next: (atualizado) => {
        this.candidatos.update((atual) => atual.map((candidato) => (candidato.id === id ? atualizado : candidato)));
      },
    });
  }

  /** Baixa o currículo original — via `HttpClient` (não um `<a href>`
   * direto), porque a rota exige o token de autenticação no header, que só
   * a chamada passando pelo interceptor de auth carrega. Recebe só
   * `id`/`nome` (não o `Candidato` inteiro) pra também servir a tela de
   * busca, que lida com `ResultadoBusca`, não com `Candidato`. */
  baixarCurriculo(candidato: { id: number; nome: string }): void {
    this.http
      .get(`${MCP_API_BASE_URL}/api/rh/candidatos/${candidato.id}/curriculo`, {
        observe: 'response',
        responseType: 'blob',
      })
      .subscribe({
        next: (resposta) => {
          const blob = resposta.body;
          if (!blob) {
            return;
          }
          const nomeArquivo = extrairNomeArquivo(
            resposta.headers.get('content-disposition'),
            `${candidato.nome}.pdf`,
          );
          baixarBlob(blob, nomeArquivo);
        },
      });
  }

  carregarCandidatos(status?: StatusCandidato): void {
    this.http
      .get<Candidato[]>(`${MCP_API_BASE_URL}/api/rh/candidatos`, { params: status ? { status } : {} })
      .subscribe({
        next: (candidatos) => this.candidatos.set(candidatos),
        error: () => this.candidatos.set([]),
      });
  }

  iniciarAnalise(arquivo: File): void {
    const id = `analise-${Date.now()}-${Math.round(Math.random() * 1000)}`;
    this.emAndamento.update((atual) => [...atual, { id, nomeArquivo: arquivo.name }]);

    const formData = new FormData();
    formData.append('arquivo', arquivo);

    this.http.post<Candidato>(`${MCP_API_BASE_URL}/api/rh/candidatos/analisar`, formData).subscribe({
      next: (candidato) => this.concluirAnalise(id, candidato),
      error: (erro: HttpErrorResponse) => this.falharAnalise(id, erro),
    });
  }

  /** concluirAnalise e falharAnalise só são usadas por iniciarAnalise,
   * logo depois dela (nessa ordem — sucesso e falha do mesmo POST). */
  private concluirAnalise(analiseId: string, candidato: Candidato): void {
    this.emAndamento.update((atual) => atual.filter((item) => item.id !== analiseId));
    // Backend faz upsert (`criar_candidato`): currículo repetido volta com o
    // MESMO id de um candidato que já está nesta lista, em vez de um id novo.
    // Sem filtrar o id existente aqui, ele entraria duplicado nessa lista
    // local mesmo o banco tendo só uma linha — daí o "aparece duas vezes na
    // tela" mesmo sem duplicata nenhuma no Postgres.
    this.candidatos.update((atual) => [candidato, ...atual.filter((item) => item.id !== candidato.id)]);
    this.notificacoes.update((atual) => [
      ...atual,
      { id: `notif-${candidato.id}`, candidatoId: candidato.id, candidatoNome: candidato.nome, vista: false },
    ]);
  }

  private falharAnalise(analiseId: string, erro: HttpErrorResponse): void {
    this.emAndamento.update((atual) => atual.filter((item) => item.id !== analiseId));
    this.erros.update((atual) => [
      ...atual,
      { id: `erro-${analiseId}`, mensagem: mensagemErro(erro, 'Não foi possível analisar o currículo.'), vista: false },
    ]);
  }

  marcarComoVista(notificacaoId: string): void {
    this.notificacoes.update((atual) =>
      atual.map((item) => (item.id === notificacaoId ? { ...item, vista: true } : item)),
    );
  }

  marcarErroComoVisto(erroId: string): void {
    this.erros.update((atual) => atual.map((item) => (item.id === erroId ? { ...item, vista: true } : item)));
  }

  /** Marca toda notificação/erro pendente como visto de uma vez — chamado
   * ao clicar no grupo "RH" da sidebar (ver `Sidebar.toggleRh`), pra a
   * bolinha vermelha sumir assim que o usuário entra no módulo, sem
   * precisar ver toast por toast. */
  marcarTudoComoVisto(): void {
    this.notificacoes.update((atual) => atual.map((item) => ({ ...item, vista: true })));
    this.erros.update((atual) => atual.map((item) => ({ ...item, vista: true })));
  }
}
