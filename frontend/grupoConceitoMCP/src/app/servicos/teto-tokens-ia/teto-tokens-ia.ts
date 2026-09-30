import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, tap } from 'rxjs';
import { MCP_API_BASE_URL } from '../../app-config';

export interface RespostaTetoTokensIa {
  dominio: string;
  teto_tokens_diario: number;
  tokens_hoje: number;
}

/** Teto diário de tokens de IA, por departamento (`server/ia/teto_tokens.py`)
 * — leitura liberada a qualquer usuário do módulo do domínio pedido,
 * escrita restrita a quem administra ESSE domínio (ou desenvolvedor).
 * `dominio` é sempre passado explicitamente pelo chamador (`'ti'`/`'rh'`
 * hoje), o mesmo serviço cobre a tela de Provedores de LLM (TI) e a
 * engrenagem da Home (RH), já que os dois só diferem no domínio. Mesmo
 * padrão de `ConfiguracoesTi`: os signals só mudam com a resposta do
 * servidor, `salvando`/erro ficam por conta de quem chama `salvar`. */
@Injectable({ providedIn: 'root' })
export class TetoTokensIa {
  private readonly http = inject(HttpClient);

  readonly teto = signal<number | null>(null);
  readonly tokensHoje = signal<number>(0);

  private aplicar(resposta: RespostaTetoTokensIa): void {
    this.teto.set(resposta.teto_tokens_diario);
    this.tokensHoje.set(resposta.tokens_hoje);
  }

  carregar(dominio: string): void {
    this.http
      .get<RespostaTetoTokensIa>(`${MCP_API_BASE_URL}/api/ia/teto-tokens/${encodeURIComponent(dominio)}`)
      .subscribe({ next: (resposta) => this.aplicar(resposta) });
  }

  salvar(dominio: string, teto: number): Observable<RespostaTetoTokensIa> {
    return this.http
      .put<RespostaTetoTokensIa>(`${MCP_API_BASE_URL}/api/ia/teto-tokens/${encodeURIComponent(dominio)}`, {
        teto_tokens_diario: teto,
      })
      .pipe(tap((resposta) => this.aplicar(resposta)));
  }
}
