import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MCP_API_BASE_URL } from '../../../../app-config';
import { Botao } from '../../../../componentes/botao/botao';
import { Busca } from '../../../../componentes/busca/busca';
import { EstadoVazio } from '../../../../componentes/estado-vazio/estado-vazio';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';
import { OpcaoSelectBusca, SelectBusca } from '../../../../componentes/select-busca/select-busca';
import { Selo } from '../../../../componentes/selo/selo';
import { mensagemErro } from '../../../../servicos/mensagens-erro/mensagens-erro';
import { Toasts } from '../../../../servicos/toasts/toasts';

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

interface ResumoPrecisao {
  total_revisado: number;
  aceitas: number;
  corrigidas: number;
  precisao_percentual: number | null;
}

/** MÓDULO FINANCEIRO — TELA "CLASSIFICAÇÃO CONTÁBIL" (2026-08)
 *
 * Item "Classificação Contábil Autônoma" da planilha de demandas de IA
 * do Financeiro. Sem IA de propósito: a sugestão de conta vem por
 * semelhança de texto do histórico do lançamento contra os lançamentos
 * JÁ classificados (`agent/financeiro/classificacao_contabil.py`) — só
 * sugere uma conta com precedente real, nunca inventa código.
 *
 * Aceitar/Corrigir (2026-08): "99% de precisão" na planilha era só uma
 * esperança até aqui — sem nenhum jeito de confirmar se a sugestão estava
 * certa, ninguém sabia a taxa de acerto real. Cada aceite/correção fica
 * registrado no nosso Postgres (nunca no Oracle/STAGE — sempre só leitura
 * lá, ver `tools/financeiro/classificacao_revisoes.py`), e o indicador de
 * precisão no topo da tela mostra o número medido de verdade. Lançamento
 * já revisado some da lista na próxima análise (filtrado no servidor). */
@Component({
  selector: 'app-classificacao-contabil',
  imports: [Botao, Busca, EstadoVazio, FormsModule, ModuloHeader, SelectBusca, Selo],
  templateUrl: './classificacao-contabil.html',
  styleUrl: './classificacao-contabil.scss',
})
export class ClassificacaoContabil {
  private readonly http = inject(HttpClient);
  private readonly toasts = inject(Toasts);

  protected readonly filiais = signal<OpcaoSelectBusca[]>([]);
  protected readonly filiaisSelecionadas = signal<string[]>([]);
  protected readonly analisando = signal(false);
  protected readonly jaAnalisou = signal(false);
  protected readonly sugestoes = signal<SugestaoClassificacao[]>([]);
  protected readonly erro = signal<string | null>(null);
  protected readonly precisao = signal<ResumoPrecisao | null>(null);

  protected readonly termoBusca = signal('');
  protected readonly sugestoesFiltradas = computed(() => {
    const termo = this.termoBusca().trim().toLowerCase();
    if (!termo) {
      return this.sugestoes();
    }
    return this.sugestoes().filter(
      (sugestao) =>
        sugestao.historico.toLowerCase().includes(termo) ||
        sugestao.conta_sugerida.toLowerCase().includes(termo) ||
        (sugestao.conta_descricao_sugerida?.toLowerCase().includes(termo) ?? false),
    );
  });

  protected readonly revisando = signal<Set<string>>(new Set());
  protected readonly corrigindoChave = signal<string | null>(null);
  protected readonly contaCorretaTexto = signal('');

  constructor() {
    this.carregarFiliais();
    this.carregarPrecisao();
  }

  protected analisar(): void {
    if (!this.filiaisSelecionadas().length || this.analisando()) {
      return;
    }

    this.analisando.set(true);
    this.erro.set(null);
    this.termoBusca.set('');

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

  protected abrirCorrigir(sugestao: SugestaoClassificacao): void {
    this.corrigindoChave.set(this.chave(sugestao));
    this.contaCorretaTexto.set('');
  }

  protected aceitar(sugestao: SugestaoClassificacao): void {
    this.enviarRevisao(sugestao, 'aceita', null);
  }

  protected chave(sugestao: SugestaoClassificacao): string {
    return `${sugestao.documento}-${sugestao.linha}`;
  }

  protected confirmarCorrigir(sugestao: SugestaoClassificacao): void {
    this.enviarRevisao(sugestao, 'corrigida', this.contaCorretaTexto().trim() || null);
  }

  protected fecharCorrigir(): void {
    this.corrigindoChave.set(null);
  }

  private carregarFiliais(): void {
    this.http.get<Filial[]>(`${MCP_API_BASE_URL}/api/financeiro/filiais`).subscribe({
      next: (filiais) => {
        this.filiais.set(filiais.map((filial) => ({ valor: filial.codigo, rotulo: filial.nome })));
      },
      error: () => this.filiais.set([]),
    });
  }

  private carregarPrecisao(): void {
    this.http
      .get<ResumoPrecisao>(`${MCP_API_BASE_URL}/api/financeiro/classificacao-contabil/precisao`)
      .subscribe({
        next: (precisao) => this.precisao.set(precisao),
        error: () => this.precisao.set(null),
      });
  }

  // enviarRevisao é usada por aceitar e confirmarCorrigir, logo antes dela.
  private enviarRevisao(
    sugestao: SugestaoClassificacao,
    resultado: 'aceita' | 'corrigida',
    contaCorreta: string | null,
  ): void {
    const chave = this.chave(sugestao);
    if (this.revisando().has(chave)) {
      return;
    }

    this.revisando.update((atual) => new Set(atual).add(chave));
    this.http
      .post(`${MCP_API_BASE_URL}/api/financeiro/classificacao-contabil/revisar`, {
        documento: sugestao.documento,
        linha: sugestao.linha,
        conta_sugerida: sugestao.conta_sugerida,
        resultado,
        conta_correta: contaCorreta,
      })
      .subscribe({
        next: () => {
          this.sugestoes.update((atual) => atual.filter((item) => this.chave(item) !== chave));
          this.revisando.update((atual) => {
            const novo = new Set(atual);
            novo.delete(chave);
            return novo;
          });
          this.corrigindoChave.set(null);
          this.toasts.sucesso(
            resultado === 'aceita' ? 'Sugestão confirmada.' : 'Sugestão marcada como corrigida.',
          );
          this.carregarPrecisao();
        },
        error: (erro: HttpErrorResponse) => {
          this.revisando.update((atual) => {
            const novo = new Set(atual);
            novo.delete(chave);
            return novo;
          });
          this.toasts.erro(mensagemErro(erro, 'Não foi possível registrar a revisão.'));
        },
      });
  }

  protected formatarValor(valor: number): string {
    return valor.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  }

  protected tomConfianca(confiancaPercentual: number): 'ok' | 'atencao' {
    return confiancaPercentual >= 99 ? 'ok' : 'atencao';
  }
}
