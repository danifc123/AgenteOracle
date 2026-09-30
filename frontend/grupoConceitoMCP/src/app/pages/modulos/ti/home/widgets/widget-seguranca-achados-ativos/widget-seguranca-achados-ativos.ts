import { HttpClient } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../../../../../app-config';
import { CartaoKpi } from '../../../../../../componentes/cartao-kpi/cartao-kpi';

const URL_SEGURANCA_HISTORICO = `${MCP_API_BASE_URL}/api/ti/seguranca/historico`;

/** Reaproveita `GET /api/ti/seguranca/historico` (mesma rota que alimenta a
 * tela "Segurança de TI") — pra quem não é desenvolvedor essa rota já
 * devolve só os achados ATIVOS, então contar o tamanho da lista aqui é
 * seguro sem precisar filtrar de novo. Achados de login/acesso suspeito no
 * Protheus e no próprio AgenteOracle entram juntos (ver `AchadoSeguranca.sistema`
 * no backend). */
@Component({
  selector: 'app-widget-seguranca-achados-ativos',
  imports: [CartaoKpi],
  templateUrl: './widget-seguranca-achados-ativos.html',
})
export class WidgetSegurancaAchadosAtivos {
  private readonly http = inject(HttpClient);

  protected readonly achados = signal<unknown[]>([]);
  protected readonly total = computed(() => this.achados().length);

  constructor() {
    this.http.get<unknown[]>(URL_SEGURANCA_HISTORICO).subscribe({
      next: (achados) => this.achados.set(achados),
    });
  }
}
