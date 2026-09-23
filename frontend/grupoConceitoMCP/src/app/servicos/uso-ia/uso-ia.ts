import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../app-config';

export interface LinhaUsoIa {
  provedor: string;
  modelo: string;
  chamadas: number;
  tokens_entrada: number;
  tokens_saida: number;
  tokens_raciocinio: number;
  tokens_total: number;
  /** `null` quando essa linha não bate com nenhum LLM cadastrado hoje —
   * chamada antiga, provedor removido do cadastro, ou o fallback "Ollama
   * (padrão)" (sem cadastro, nunca tem preço). Ver
   * `server/ti/uso_ia.py::_custo_e_moeda` no backend. */
  custo_estimado: number | null;
  moeda: string | null;
}

export interface LinhaUsoIaPorUsuario {
  usuario_id: string;
  nome: string;
  chamadas: number;
  tokens_entrada: number;
  tokens_saida: number;
  tokens_raciocinio: number;
  tokens_total: number;
}

export interface LinhaUsoIaPorDia {
  data: string;
  chamadas: number;
  tokens_entrada: number;
  tokens_saida: number;
  tokens_total: number;
}

export interface ChamadosIaResposta {
  total_chamados: number;
  avaliados_insuficientes: number;
  com_fallback_embedding: number;
  duracao_media_ms: number;
}

export interface UsoIaResposta {
  consumo: LinhaUsoIa[];
  /** Já vem ordenado do backend, maior consumo primeiro — não reordenar de novo no front. */
  por_usuario: LinhaUsoIaPorUsuario[];
  /** Já vem ordenado do mais antigo pro mais recente — pronto pra virar `SerieGrafico`. */
  por_dia: LinhaUsoIaPorDia[];
  tokens_hoje_por_dominio: Record<string, number>;
  chamados_ia: ChamadosIaResposta;
}

const URL_USO_IA = `${MCP_API_BASE_URL}/api/ti/uso-ia`;

/** Consumo de tokens por provedor/modelo, por usuário e por dia (últimos
 * 30 dias), mais o uso de IA nos chamados do TI — só leitura, cobre TI + RH
 * juntos (a auditoria de onde vem é única pro processo inteiro, ver
 * `tools/ia/auditoria_externa.py` no backend). Só desenvolvedor consegue
 * chamar essa rota (403 pra qualquer outro usuário do módulo TI) — usado
 * tanto pela página Tokens quanto pelo bloco "Consumo de IA" (atrás de
 * `*appSoDev`) no lobby do TI. */
@Injectable({ providedIn: 'root' })
export class UsoIa {
  private readonly http = inject(HttpClient);

  readonly consumo = signal<LinhaUsoIa[]>([]);
  readonly porUsuario = signal<LinhaUsoIaPorUsuario[]>([]);
  readonly porDia = signal<LinhaUsoIaPorDia[]>([]);
  readonly tokensHojePorDominio = signal<Record<string, number>>({});
  readonly chamadosIa = signal<ChamadosIaResposta | null>(null);

  carregar(): void {
    this.http.get<UsoIaResposta>(URL_USO_IA).subscribe({
      next: (resposta) => {
        this.consumo.set(resposta.consumo);
        this.porUsuario.set(resposta.por_usuario);
        this.porDia.set(resposta.por_dia);
        this.tokensHojePorDominio.set(resposta.tokens_hoje_por_dominio);
        this.chamadosIa.set(resposta.chamados_ia);
      },
    });
  }
}
