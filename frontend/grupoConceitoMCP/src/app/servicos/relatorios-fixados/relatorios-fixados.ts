import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../app-config';

interface RespostaRelatoriosFixados {
  nomes: string[];
}

/** Relatórios/rotinas "fixados" por usuário (Financeiro e Estoque) —
 * autoatendimento (o backend usa o usuário do token, `modulo` vai na
 * própria URL). Substitui a leitura/escrita direta em `localStorage` que
 * `financeiro.ts` e `estoque/especifico-grupo-conceito.ts` faziam cada um
 * por conta própria (lógica idêntica duplicada nos dois) — agora
 * persistido no backend (`server/auth/relatorios_fixados.py`), então
 * sobrevive a troca de máquina/limpeza de navegador, e um serviço só
 * cobre os dois lugares.
 *
 * `modulo` é sempre passado explicitamente pelo chamador (não fica
 * guardado no serviço) — é a mesma string que já era a chave do
 * localStorage antes (ex: `"financeiro:cadastros:fixados"`), porque cada
 * tela pode ter seu próprio módulo/rota. */
@Injectable({ providedIn: 'root' })
export class RelatoriosFixados {
  private readonly http = inject(HttpClient);

  private readonly _nomes = signal<string[]>([]);
  readonly nomes = this._nomes.asReadonly();

  carregar(modulo: string): void {
    this.http.get<RespostaRelatoriosFixados>(`${MCP_API_BASE_URL}/api/relatorios-fixados/${encodeURIComponent(modulo)}`)
      .subscribe({
        next: (resposta) => this._nomes.set(resposta.nomes),
        error: () => this._nomes.set([]),
      });
  }

  /** Atualização otimista (mesmo padrão de `LayoutHome.salvarAgora`) —
   * a tela já reordena/filtra na hora, grava no servidor em paralelo. */
  salvar(modulo: string, nomes: string[]): void {
    this._nomes.set(nomes);
    this.http
      .put<RespostaRelatoriosFixados>(`${MCP_API_BASE_URL}/api/relatorios-fixados/${encodeURIComponent(modulo)}`, {
        nomes,
      })
      .subscribe({ next: (resposta) => this._nomes.set(resposta.nomes) });
  }
}
