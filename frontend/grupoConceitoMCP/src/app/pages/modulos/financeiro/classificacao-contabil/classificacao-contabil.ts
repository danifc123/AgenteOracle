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

interface SugestaoClassificacao {
  documento: string;
  linha: string;
  historico: string;
  valor: number;
  data_movimentacao: string;
  conta_sugerida: string;
  conta_descricao_sugerida: string | null;
  confianca_percentual: number;
  suporte_historico: number;
}

/** MÓDULO FINANCEIRO — TELA "CLASSIFICAÇÃO CONTÁBIL" (2026-08)
 *
 * Item "Classificação Contábil Autônoma" da planilha de demandas de IA
 * do Financeiro. Sem IA de propósito: a sugestão de conta vem por
 * semelhança de texto do histórico do lançamento contra os lançamentos
 * JÁ classificados (`agent/financeiro/classificacao_contabil.py`) — só
 * sugere uma conta com precedente real, nunca inventa código. */
@Component({
  selector: 'app-classificacao-contabil',
  imports: [Botao, EstadoVazio, ModuloHeader, SelectBusca],
  templateUrl: './classificacao-contabil.html',
  styleUrl: './classificacao-contabil.scss',
})
export class ClassificacaoContabil {
  private readonly http = inject(HttpClient);

  protected readonly filiais = signal<OpcaoSelectBusca[]>([]);
  protected readonly filiaisSelecionadas = signal<string[]>([]);
  protected readonly analisando = signal(false);
  protected readonly jaAnalisou = signal(false);
  protected readonly sugestoes = signal<SugestaoClassificacao[]>([]);
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
      .get<SugestaoClassificacao[]>(`${MCP_API_BASE_URL}/api/financeiro/classificacao-contabil`, {
        params: { filial: this.filiaisSelecionadas().join(',') },
      })
      .subscribe({
        next: (sugestoes) => {
          this.sugestoes.set(sugestoes);
          this.jaAnalisou.set(true);
          this.analisando.set(false);
        },
        error: (erro: HttpErrorResponse) => {
          this.erro.set(mensagemErro(erro, 'Não foi possível analisar os lançamentos.'));
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

  protected classeConfianca(confiancaPercentual: number): string {
    return confiancaPercentual >= 99 ? 'badge-confianca--alta' : 'badge-confianca--media';
  }
}
