import { HttpClient } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../../../../../app-config';
import { CartaoKpi } from '../../../../../../componentes/cartao-kpi/cartao-kpi';
import { gerarPrevisaoStream } from '../../../../../../servicos/previsao-stream/previsao-stream';

interface Filial {
  codigo: string;
}

interface ItemMes {
  valor: number;
}

interface RespostaVendas {
  historico: ItemMes[];
}

const URL_FILIAIS = `${MCP_API_BASE_URL}/api/financeiro/filiais`;
const URL_PREVISAO = `${MCP_API_BASE_URL}/api/financeiro/previsao/vendas`;

/** Autossuficiente: sem seletor de filial — pede a previsão pra TODAS as
 * filiais liberadas pro usuário logado (`/api/financeiro/filiais`, que já
 * exclui as bloqueadas). Mesma fórmula da tela de Vendas
 * (`vendas.ts::faturamentoTotal`): soma do `historico` (últimos 12 meses,
 * conforme o backend). Ignora as etapas de progresso do streaming (widget
 * só mostra o resultado final). */
@Component({
  selector: 'app-widget-faturamento-total',
  imports: [CartaoKpi],
  templateUrl: './widget-faturamento-total.html',
})
export class WidgetFaturamentoTotal {
  private readonly http = inject(HttpClient);

  protected readonly faturamentoTotal = signal<number>(0);

  constructor() {
    this.http.get<Filial[]>(URL_FILIAIS).subscribe({
      next: (filiais) => this.gerarPrevisao(filiais.map((filial) => filial.codigo)),
    });
  }

  private async gerarPrevisao(codigosFiliais: string[]): Promise<void> {
    if (codigosFiliais.length === 0) {
      return;
    }
    try {
      const resposta = await gerarPrevisaoStream<RespostaVendas>(
        this.http,
        URL_PREVISAO,
        { filial: codigosFiliais.join(',') },
        () => undefined,
      );
      this.faturamentoTotal.set(resposta.historico.reduce((soma, item) => soma + item.valor, 0));
    } catch {
      // Widget sem estado de erro (mesmo espírito dos widgets de TI, que
      // também não mostram falha de carregamento) — fica em 0 até a
      // próxima vez que a Home for recarregada.
    }
  }
}
