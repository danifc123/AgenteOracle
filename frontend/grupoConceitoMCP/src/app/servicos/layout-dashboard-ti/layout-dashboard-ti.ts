import { HttpClient, HttpContext } from '@angular/common/http';
import { DestroyRef, Injectable, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../app-config';
import { ItemLayoutTi } from '../../pages/modulos/ti/home/widgets/catalogo-widgets-ti';
import { TOAST_DESATIVADO } from '../toast.interceptor/toast.interceptor';

export interface LayoutDashboardTiResposta {
  widgets: ItemLayoutTi[];
}

const URL_DASHBOARD = `${MCP_API_BASE_URL}/api/ti/dashboard`;

// Arrastar gera várias posições intermediárias — só grava quando o usuário
// PARA de arrastar por esse tanto, não a cada pixel.
const DEBOUNCE_SALVAR_MS = 600;

/** Layout de indicadores da Home do TI, personalizável por usuário —
 * autoatendimento (o backend usa o usuário do token, sem `{id}` na URL). */
@Injectable({ providedIn: 'root' })
export class LayoutDashboardTi {
  private readonly http = inject(HttpClient);

  readonly widgets = signal<ItemLayoutTi[]>([]);

  private idDebounce: ReturnType<typeof setTimeout> | null = null;

  constructor() {
    inject(DestroyRef).onDestroy(() => {
      if (this.idDebounce !== null) {
        clearTimeout(this.idDebounce);
      }
    });
  }

  carregar(): void {
    this.http.get<LayoutDashboardTiResposta>(URL_DASHBOARD).subscribe({
      next: (resposta) => this.widgets.set(resposta.widgets),
    });
  }

  /** Chamado a cada solta de arrastar — atualização otimista local na hora
   * (a ordem já muda na tela), grava no servidor só depois do debounce. */
  agendarSalvar(widgets: ItemLayoutTi[]): void {
    this.widgets.set(widgets);
    if (this.idDebounce !== null) {
      clearTimeout(this.idDebounce);
    }
    this.idDebounce = setTimeout(() => this.salvarAgora(widgets), DEBOUNCE_SALVAR_MS);
  }

  /** Chamado direto (sem debounce) por adicionar/remover/redimensionar
   * indicador — clique explícito e discreto, não precisa esperar. */
  salvarAgora(widgets: ItemLayoutTi[]): void {
    this.widgets.set(widgets);
    this.http
      .put<LayoutDashboardTiResposta>(
        URL_DASHBOARD,
        { widgets },
        { context: new HttpContext().set(TOAST_DESATIVADO, true) },
      )
      .subscribe({ next: (resposta) => this.widgets.set(resposta.widgets) });
  }
}
