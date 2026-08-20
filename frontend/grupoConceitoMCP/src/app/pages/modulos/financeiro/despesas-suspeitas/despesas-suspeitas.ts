import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../../../app-config';
import { Botao } from '../../../../componentes/botao/botao';
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
  fornecedor_nome: string;
  valor: number;
  documentos: string;
  descricao: string;
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
  imports: [Botao, EstadoVazio, ModuloHeader, SelectBusca],
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

  protected formatarValor(valor: number): string {
    return valor.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  }

  protected rotuloTipo(tipo: TipoAchadoDespesa): string {
    return ROTULOS_TIPO[tipo];
  }
}
