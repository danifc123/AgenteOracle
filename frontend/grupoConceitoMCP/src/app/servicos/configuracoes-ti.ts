import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../app-config';

interface ConfiguracoesTiResposta {
  usar_ia_avaliacao_chamado: boolean;
}

/** Flag "usar IA na avaliação de chamados" (TI → Auditoria de Chamados) —
 * persistida no backend (`ti_configuracoes`), pra o time de TI poder
 * desligar a IA nessa etapa sem depender de deploy/reinício de servidor.
 * Sem chamada ao Ollama, a avaliação cai numa regra de contagem de
 * palavras (ver `agent/ti/qualidade_chamado.py`). */
@Injectable({ providedIn: 'root' })
export class ConfiguracoesTi {
  private readonly http = inject(HttpClient);

  readonly usarIaAvaliacaoChamado = signal(true);

  carregar(): void {
    this.http.get<ConfiguracoesTiResposta>(`${MCP_API_BASE_URL}/api/ti/configuracoes`).subscribe({
      next: (resposta) => this.usarIaAvaliacaoChamado.set(resposta.usar_ia_avaliacao_chamado),
    });
  }

  definirUsarIa(valor: boolean) {
    return this.http.put<ConfiguracoesTiResposta>(`${MCP_API_BASE_URL}/api/ti/configuracoes`, {
      usar_ia_avaliacao_chamado: valor,
    });
  }
}
