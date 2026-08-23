import { DecimalPipe } from '@angular/common';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../../../app-config';
import { Botao } from '../../../../componentes/botao/botao';
import { Dialog } from '../../../../componentes/dialog/dialog';
import { EstadoVazio } from '../../../../componentes/estado-vazio/estado-vazio';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';
import { OpcaoSelectBusca, SelectBusca } from '../../../../componentes/select-busca/select-busca';
import { mensagemErro } from '../../../../servicos/mensagens-erro';

interface Filial {
  codigo: string;
  nome: string;
}

type TipoAchadoDespesa = 'duplicidade' | 'anomalia_valor';

interface AchadoDespesa {
  tipo: TipoAchadoDespesa;
  fornecedor_codigo: string;
  fornecedor_nome: string;
  valor: number;
  documentos: string;
  descricao: string;
  data_emissao_min: string;
  data_emissao_max: string;
  /** Só existe pra `anomalia_valor` — o candidato de duplicidade não tem
   * grupo/média, é uma comparação direta entre dois títulos. */
  natureza_descricao: string | null;
  media_grupo: number | null;
}

const ROTULOS_TIPO: Record<TipoAchadoDespesa, string> = {
  duplicidade: 'Possível duplicidade',
  anomalia_valor: 'Valor fora do padrão',
};

/** MÓDULO FINANCEIRO — TELA "DESPESAS SUSPEITAS" (2026-08)
 *
 * Item "Auditoria Inteligente de Despesas" da planilha de demandas de IA.
 * Roda sob demanda (sem job em segundo plano): busca os títulos a pagar
 * dos últimos 90 dias das filiais selecionadas, acha candidatos de
 * duplicidade/anomalia de valor de forma determinística e manda pra IA
 * revisar/descrever (`agent/financeiro/despesas_suspeitas.py`) — a IA
 * nunca decide sozinha o que é suspeito, só julga candidato já real. */
@Component({
  selector: 'app-despesas-suspeitas',
  imports: [Botao, DecimalPipe, Dialog, EstadoVazio, ModuloHeader, SelectBusca],
  templateUrl: './despesas-suspeitas.html',
  styleUrl: './despesas-suspeitas.scss',
})
export class DespesasSuspeitas {
  private readonly http = inject(HttpClient);

  protected readonly filiais = signal<OpcaoSelectBusca[]>([]);
  protected readonly filiaisSelecionadas = signal<string[]>([]);
  protected readonly analisando = signal(false);
  protected readonly jaAnalisou = signal(false);
  protected readonly achados = signal<AchadoDespesa[]>([]);
  protected readonly erro = signal<string | null>(null);

  protected readonly achadoDetalhado = signal<AchadoDespesa | null>(null);

  /** Só faz sentido pra `anomalia_valor` (tem `media_grupo`) — quanto o
   * valor encontrado ficou acima da média do grupo, em %, pra dar noção
   * de escala além do número cru ("6,6x acima" fala mais rápido que "R$
   * 7.200 vs média R$ 838"). */
  protected readonly percentualAcimaDaMedia = computed(() => {
    const achado = this.achadoDetalhado();
    if (!achado?.media_grupo) {
      return null;
    }
    return ((achado.valor - achado.media_grupo) / achado.media_grupo) * 100;
  });

  /** Largura da barra "Média do grupo" no comparativo visual, em % —
   * a barra "Este título" sempre ocupa 100% (é sempre a maior, por
   * definição do próprio algoritmo de anomalia). Piso de 4% pra a barra
   * da média nunca sumir visualmente quando o desvio é gigante (ex: média
   * 12x menor que o valor encontrado). */
  protected readonly larguraBarraMedia = computed(() => {
    const achado = this.achadoDetalhado();
    if (!achado?.media_grupo || achado.valor <= 0) {
      return 0;
    }
    return Math.max(4, Math.min(100, (achado.media_grupo / achado.valor) * 100));
  });

  constructor() {
    this.carregarFiliais();
  }

  protected analisar(): void {
    if (!this.filiaisSelecionadas().length || this.analisando()) {
      return;
    }

    this.analisando.set(true);
    this.erro.set(null);

    this.http
      .get<AchadoDespesa[]>(`${MCP_API_BASE_URL}/api/financeiro/despesas-suspeitas`, {
        params: { filial: this.filiaisSelecionadas().join(',') },
      })
      .subscribe({
        next: (achados) => {
          this.achados.set(achados);
          this.jaAnalisou.set(true);
          this.analisando.set(false);
        },
        error: (erro: HttpErrorResponse) => {
          this.erro.set(mensagemErro(erro, 'Não foi possível analisar as despesas.'));
          this.analisando.set(false);
        },
      });
  }

  private carregarFiliais(): void {
    this.http.get<Filial[]>(`${MCP_API_BASE_URL}/api/financeiro/filiais`).subscribe({
      next: (filiais) => {
        this.filiais.set(filiais.map((filial) => ({ valor: filial.codigo, rotulo: filial.nome })));
      },
      error: () => this.filiais.set([]),
    });
  }

  protected abrirDetalhamento(achado: AchadoDespesa): void {
    this.achadoDetalhado.set(achado);
  }

  protected fecharDetalhamento(): void {
    this.achadoDetalhado.set(null);
  }

  protected formatarData(data: string): string {
    return new Date(`${data}T00:00:00`).toLocaleDateString('pt-BR');
  }

  /** Faixa "23/07 a 05/08" quando as duas datas diferem (caso normal de
   * duplicidade — os documentos não saem todos no mesmo dia), ou uma data
   * só quando coincidem (sempre o caso em anomalia_valor, que compara um
   * único título contra a média do grupo). */
  protected formatarFaixaEmissao(achado: AchadoDespesa): string {
    const minimo = this.formatarData(achado.data_emissao_min);
    const maximo = this.formatarData(achado.data_emissao_max);
    return minimo === maximo ? minimo : `${minimo} a ${maximo}`;
  }

  /** `documentos` chega como string única já formatada pelo backend
   * ("NF-001, NF-002, NF-003") — separa de volta pra virar itens
   * individuais na timeline de duplicidade. */
  protected listaDocumentos(achado: AchadoDespesa): string[] {
    return achado.documentos.split(', ');
  }

  protected formatarValor(valor: number): string {
    return valor.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  }

  protected rotuloTipo(tipo: TipoAchadoDespesa): string {
    return ROTULOS_TIPO[tipo];
  }
}
