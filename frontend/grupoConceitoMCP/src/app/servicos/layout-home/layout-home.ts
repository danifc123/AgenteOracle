import { HttpClient, HttpContext } from '@angular/common/http';
import { DestroyRef, Injectable, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../app-config';
import { ItemLayoutHome } from '../../pages/home/catalogo-widgets-home';
import { TOAST_DESATIVADO } from '../toast.interceptor/toast.interceptor';

export interface LayoutHomeResposta {
  widgets: ItemLayoutHome[];
}

const URL_DASHBOARD = `${MCP_API_BASE_URL}/api/home/dashboard`;

// Arrastar gera várias posições intermediárias — só grava quando o usuário
// PARA de arrastar por esse tanto, não a cada pixel.
const DEBOUNCE_SALVAR_MS = 600;

/** Layout de indicadores da Home única, personalizável por usuário —
 * autoatendimento (o backend usa o usuário do token, sem `{id}` na URL).
 * Mesmo molde de `LayoutDashboardTi` (que este serviço substitui, ver
 * `server/home/dashboard.py` no backend), generalizado pra ids namespaced
 * cross-módulo em vez de só TI. */
@Injectable({ providedIn: 'root' })
export class LayoutHome {
  private readonly http = inject(HttpClient);

  readonly widgets = signal<ItemLayoutHome[]>([]);

  private idDebounce: ReturnType<typeof setTimeout> | null = null;

  constructor() {
    inject(DestroyRef).onDestroy(() => {
      if (this.idDebounce !== null) {
        clearTimeout(this.idDebounce);
      }
    });
  }

  carregar(): void {
    this.http.get<LayoutHomeResposta>(URL_DASHBOARD).subscribe({
      next: (resposta) => this.widgets.set(resposta.widgets),
    });
  }

  /** Chamado a cada solta de arrastar — atualização otimista local na hora
   * (a ordem já muda na tela), grava no servidor só depois do debounce. */
  agendarSalvar(widgets: ItemLayoutHome[]): void {
    this.widgets.set(widgets);
    if (this.idDebounce !== null) {
      clearTimeout(this.idDebounce);
    }
    this.idDebounce = setTimeout(() => this.salvarAgora(widgets), DEBOUNCE_SALVAR_MS);
  }

  /** Chamado direto (sem debounce) por adicionar/remover/redimensionar
   * indicador — clique explícito e discreto, não precisa esperar. */
  salvarAgora(widgets: ItemLayoutHome[]): void {
    this.widgets.set(widgets);
    this.http
      .put<LayoutHomeResposta>(
        URL_DASHBOARD,
        { widgets },
        { context: new HttpContext().set(TOAST_DESATIVADO, true) },
      )
      .subscribe({ next: (resposta) => this.widgets.set(resposta.widgets) });
  }
}
