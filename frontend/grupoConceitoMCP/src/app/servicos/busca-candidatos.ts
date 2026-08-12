import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../app-config';
import { mensagemErro } from './mensagens-erro';
import { NivelSenioridade, PerfilEstruturado } from './analise-curriculo';

export interface ResultadoBusca {
  candidato_id: number;
  nome: string;
  resumo_perfil: string;
  perfil_estruturado: PerfilEstruturado;
  nivel_senioridade: NivelSenioridade;
  area_atuacao_principal: string;
  posicao: number;
  justificativa: string;
  similaridade: number;
}

/** Busca de candidatos por IA (RAG) pra tela "Selecionar Candidato" —
 * serviço à parte de `AnaliseCurriculo` porque é uma responsabilidade
 * diferente (busca sob demanda, síncrona do ponto de vista da tela — o
 * usuário espera o resultado ali mesmo — em vez de processamento em
 * segundo plano). Busca ao vivo, sem histórico: cada chamada de `buscar`
 * substitui o resultado anterior, nada fica salvo. */
@Injectable({ providedIn: 'root' })
export class BuscaCandidatos {
  private readonly http = inject(HttpClient);

  readonly resultados = signal<ResultadoBusca[]>([]);
  readonly carregando = signal(false);
  readonly erro = signal<string | null>(null);

  buscar(descricao: string): void {
    this.carregando.set(true);
    this.erro.set(null);
    this.resultados.set([]);

    this.http
      .post<ResultadoBusca[]>(`${MCP_API_BASE_URL}/api/rh/candidatos/buscar`, { descricao })
      .subscribe({
        next: (resultados) => {
          this.resultados.set(resultados);
          this.carregando.set(false);
        },
        error: (erro: HttpErrorResponse) => {
          this.erro.set(mensagemErro(erro, 'Não foi possível buscar candidatos.'));
          this.carregando.set(false);
        },
      });
  }
}
