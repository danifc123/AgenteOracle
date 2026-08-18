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

interface ComportamentoPagamento {
  percentual_atraso_recente: number;
  percentual_atraso_anterior: number;
  dias_atraso_medio: number;
  tendencia: 'piorando' | 'estavel' | 'melhorando';
}

interface ClimaRegional {
  municipio_nome: string;
  uf: string;
  classificacao: 'seca' | 'normal' | 'excesso_chuva' | 'indisponivel';
}

interface ScoreInadimplencia {
  cliente_codigo: string;
  cliente_nome: string;
  score: number;
  comportamento: ComportamentoPagamento;
  clima: ClimaRegional | null;
  fatores: string[];
}

const ROTULOS_TENDENCIA: Record<ComportamentoPagamento['tendencia'], string> = {
  piorando: 'Piorando',
  estavel: 'Estável',
  melhorando: 'Melhorando',
};

/** MÓDULO FINANCEIRO — TELA "SCORE DE INADIMPLÊNCIA" (2026-08)
 *
 * Item "Score Preditivo de Inadimplência" da planilha de demandas de IA
 * do Financeiro (Contas a Receber e Cobrança). NÃO é um modelo de
 * machine learning treinado — é um indicador composto por regra clara
 * (comportamento de pagamento + anomalia climática regional via
 * Open-Meteo), ver `agent/financeiro/score_inadimplencia.py`. */
@Component({
  selector: 'app-score-inadimplencia',
  imports: [Botao, EstadoVazio, ModuloHeader, SelectBusca],
  templateUrl: './score-inadimplencia.html',
  styleUrl: './score-inadimplencia.scss',
})
export class ScoreInadimplenciaComponent {
  private readonly http = inject(HttpClient);

  protected readonly filiais = signal<OpcaoSelectBusca[]>([]);
  protected readonly filiaisSelecionadas = signal<string[]>([]);
  protected readonly calculando = signal(false);
  protected readonly jaCalculou = signal(false);
  protected readonly scores = signal<ScoreInadimplencia[]>([]);
  protected readonly erro = signal<string | null>(null);

  constructor() {
    this.carregarFiliais();
  }

  protected calcular(): void {
    if (!this.filiaisSelecionadas().length || this.calculando()) {
      return;
    }

    this.calculando.set(true);
    this.erro.set(null);

    this.http
      .get<ScoreInadimplencia[]>(`${MCP_API_BASE_URL}/api/financeiro/score-inadimplencia`, {
        params: { filial: this.filiaisSelecionadas().join(',') },
      })
      .subscribe({
        next: (scores) => {
          this.scores.set(scores);
          this.jaCalculou.set(true);
          this.calculando.set(false);
        },
        error: (erro: HttpErrorResponse) => {
          this.erro.set(mensagemErro(erro, 'Não foi possível calcular o score de inadimplência.'));
          this.calculando.set(false);
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

  protected rotuloTendencia(tendencia: ComportamentoPagamento['tendencia']): string {
    return ROTULOS_TENDENCIA[tendencia];
  }

  protected classeScore(score: number): string {
    if (score >= 60) {
      return 'badge-score--alto';
    }
    if (score >= 30) {
      return 'badge-score--medio';
    }
    return 'badge-score--baixo';
  }
}
