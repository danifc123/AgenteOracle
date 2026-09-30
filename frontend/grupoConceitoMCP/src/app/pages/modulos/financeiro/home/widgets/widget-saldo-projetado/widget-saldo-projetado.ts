import { HttpClient } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../../../../../app-config';
import { CartaoKpi } from '../../../../../../componentes/cartao-kpi/cartao-kpi';
import { gerarPrevisaoStream } from '../../../../../../servicos/previsao-stream/previsao-stream';

interface Filial {
  codigo: string;
}

interface FatiaApi {
  valor: number;
}

interface RespostaFluxoCaixa {
  total_a_receber: number;
  total_a_pagar: number;
  fatias_a_receber: FatiaApi[];
  fatias_a_pagar: FatiaApi[];
}

const URL_FILIAIS = `${MCP_API_BASE_URL}/api/financeiro/filiais`;
const URL_PREVISAO = `${MCP_API_BASE_URL}/api/financeiro/previsao/fluxo-caixa`;

/** Autossuficiente: sem seletor de filial (diferente da tela de Fluxo de
 * Caixa, que deixa escolher) — pede a previsão pra TODAS as filiais
 * liberadas pro usuário logado (`/api/financeiro/filiais`, que já exclui
 * as bloqueadas). Mesma fórmula da tela de Fluxo de Caixa
 * (`fluxo-caixa.ts::saldoProjetado`): soma das fatias de a receber menos a
 * soma das fatias de a pagar — não usa os campos `total_a_receber`/
 * `total_a_pagar` do topo da resposta, pra ficar idêntico ao que a tela
 * mostra. Ignora as etapas de progresso do streaming (widget só mostra o
 * resultado final). */
@Component({
  selector: 'app-widget-saldo-projetado',
  imports: [CartaoKpi],
  templateUrl: './widget-saldo-projetado.html',
})
export class WidgetSaldoProjetado {
  private readonly http = inject(HttpClient);

  protected readonly saldoProjetado = signal<number>(0);

  constructor() {
    this.http.get<Filial[]>(URL_FILIAIS).subscribe({
      next: (filiais) => this.gerarPrevisao(filiais.map((filial) => filial.codigo)),
    });
  }

  private somaFatias(fatias: FatiaApi[]): number {
    return fatias.reduce((soma, fatia) => soma + fatia.valor, 0);
  }

  private async gerarPrevisao(codigosFiliais: string[]): Promise<void> {
    if (codigosFiliais.length === 0) {
      return;
    }
    try {
      const resposta = await gerarPrevisaoStream<RespostaFluxoCaixa>(
        this.http,
        URL_PREVISAO,
        { filial: codigosFiliais.join(',') },
        () => undefined,
      );
      this.saldoProjetado.set(this.somaFatias(resposta.fatias_a_receber) - this.somaFatias(resposta.fatias_a_pagar));
    } catch {
      // Widget sem estado de erro (mesmo espírito dos widgets de TI, que
      // também não mostram falha de carregamento) — fica em 0 até a
      // próxima vez que a Home for recarregada.
    }
  }
}
