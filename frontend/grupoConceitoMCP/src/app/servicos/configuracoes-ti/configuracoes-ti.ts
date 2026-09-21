import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../app-config';

interface ConfiguracoesTiResposta {
  usar_ia_avaliacao_chamado: boolean;
  percentual_amostragem_chamados: number;
}

/** Configurações da Auditoria de Chamados (TI) — persistidas no backend
 * (`ti_configuracoes`), pra o time de TI ajustar sem depender de deploy/
 * reinício de servidor:
 * - `usarIaAvaliacaoChamado`: sem chamada ao Ollama, a avaliação cai numa regra
 *   de contagem de palavras (ver `agent/ti/qualidade_chamado.py`).
 * - `percentualAmostragemChamados` (0 a 100): que parcela dos chamados novos a
 *   IA analisa, sempre arredondando pra baixo (ver
 *   `tools/ti/amostragem_chamados.py`). 100 = todos, o comportamento de sempre. */
@Injectable({ providedIn: 'root' })
export class ConfiguracoesTi {
  private readonly http = inject(HttpClient);

  readonly usarIaAvaliacaoChamado = signal(true);
  readonly percentualAmostragemChamados = signal(100);

  carregar(): void {
    this.http.get<ConfiguracoesTiResposta>(`${MCP_API_BASE_URL}/api/ti/configuracoes`).subscribe({
      next: (resposta) => {
        this.usarIaAvaliacaoChamado.set(resposta.usar_ia_avaliacao_chamado);
        this.percentualAmostragemChamados.set(resposta.percentual_amostragem_chamados);
      },
    });
  }

  definirPercentualAmostragem(valor: number) {
    return this.http.put<ConfiguracoesTiResposta>(`${MCP_API_BASE_URL}/api/ti/configuracoes`, {
      percentual_amostragem_chamados: valor,
    });
  }

  definirUsarIa(valor: boolean) {
    return this.http.put<ConfiguracoesTiResposta>(`${MCP_API_BASE_URL}/api/ti/configuracoes`, {
      usar_ia_avaliacao_chamado: valor,
    });
  }
}
