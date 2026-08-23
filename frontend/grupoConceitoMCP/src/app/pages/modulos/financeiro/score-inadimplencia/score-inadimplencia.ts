import { HttpClient, HttpContext, HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MCP_API_BASE_URL } from '../../../../app-config';
import { Botao } from '../../../../componentes/botao/botao';
import { Dialog } from '../../../../componentes/dialog/dialog';
import { EstadoVazio } from '../../../../componentes/estado-vazio/estado-vazio';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';
import { OpcaoSelectBusca, SelectBusca } from '../../../../componentes/select-busca/select-busca';
import { mensagemErro } from '../../../../servicos/mensagens-erro';
import { TOAST_DESATIVADO } from '../../../../servicos/toast.interceptor';
import { Toasts } from '../../../../servicos/toasts';

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

interface SafraAtiva {
  cultura: string;
  safra_descricao: string;
}

interface LocalizacaoCliente {
  cidade: string | null;
  bairro: string | null;
  latitude: number | null;
  longitude: number | null;
  resolvido: boolean;
}

interface ScoreInadimplencia {
  cliente_codigo: string;
  cliente_nome: string;
  score: number;
  comportamento: ComportamentoPagamento;
  clima: ClimaRegional | null;
  safra_ativa: SafraAtiva | null;
  fatores: string[];
  localizacao: LocalizacaoCliente | null;
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
 * Open-Meteo), ver `agent/financeiro/score_inadimplencia.py`. O clima só
 * conta pontos quando o cliente está dentro da janela ativa da própria
 * safra (`safra_ativa` — cultura/safra inferida da compra mais recente
 * dele, `vw_safra_cliente`) — fora da janela crítica da lavoura, clima é
 * ruído, não sinal de risco.
 *
 * Localização do cliente é cadastrada com campos separados (cidade,
 * bairro, coordenadas) em vez de texto livre — achado desta sessão
 * testando com o usuário: a API de geocodificação trata "bairro, cidade"
 * como um nome literal só, então bairro pequeno digitado junto quase
 * nunca é encontrado. Campos separados eliminam essa adivinhação. */
@Component({
  selector: 'app-score-inadimplencia',
  imports: [Botao, Dialog, EstadoVazio, FormsModule, ModuloHeader, SelectBusca],
  templateUrl: './score-inadimplencia.html',
  styleUrl: './score-inadimplencia.scss',
})
export class ScoreInadimplenciaComponent {
  private readonly http = inject(HttpClient);
  private readonly toasts = inject(Toasts);

  protected readonly filiais = signal<OpcaoSelectBusca[]>([]);
  protected readonly filiaisSelecionadas = signal<string[]>([]);
  protected readonly calculando = signal(false);
  protected readonly jaCalculou = signal(false);
  protected readonly scores = signal<ScoreInadimplencia[]>([]);
  protected readonly erro = signal<string | null>(null);

  protected readonly clienteEmEdicao = signal<ScoreInadimplencia | null>(null);
  protected readonly formCidade = signal('');
  protected readonly formBairro = signal('');
  protected readonly formLatitude = signal('');
  protected readonly formLongitude = signal('');
  protected readonly salvandoLocalizacao = signal(false);
  protected readonly erroLocalizacao = signal<string | null>(null);

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

  protected rotuloLocalizacao(localizacao: LocalizacaoCliente): string {
    if (localizacao.cidade) {
      return localizacao.bairro
        ? `${localizacao.bairro}, ${localizacao.cidade}`
        : localizacao.cidade;
    }
    return `${localizacao.latitude}, ${localizacao.longitude}`;
  }

  protected abrirLocalizacao(item: ScoreInadimplencia): void {
    const localizacao = item.localizacao;
    this.formCidade.set(localizacao?.cidade ?? '');
    this.formBairro.set(localizacao?.bairro ?? '');
    this.formLatitude.set(localizacao?.latitude != null ? String(localizacao.latitude) : '');
    this.formLongitude.set(localizacao?.longitude != null ? String(localizacao.longitude) : '');
    this.erroLocalizacao.set(null);
    this.clienteEmEdicao.set(item);
  }

  protected fecharLocalizacao(): void {
    this.clienteEmEdicao.set(null);
  }

  protected podeSalvarLocalizacao(): boolean {
    if (this.formCidade().trim()) {
      return true;
    }
    const latitude = Number(this.formLatitude());
    const longitude = Number(this.formLongitude());
    return (
      this.formLatitude().trim() !== '' &&
      this.formLongitude().trim() !== '' &&
      !isNaN(latitude) &&
      !isNaN(longitude)
    );
  }

  protected salvarLocalizacao(): void {
    const item = this.clienteEmEdicao();
    if (!item || !this.podeSalvarLocalizacao() || this.salvandoLocalizacao()) {
      return;
    }

    const cidade = this.formCidade().trim() || null;
    const bairro = this.formBairro().trim() || null;
    const latitude = this.formLatitude().trim() !== '' ? Number(this.formLatitude()) : null;
    const longitude = this.formLongitude().trim() !== '' ? Number(this.formLongitude()) : null;

    this.salvandoLocalizacao.set(true);
    this.erroLocalizacao.set(null);
    this.http
      .post<LocalizacaoCliente>(
        `${MCP_API_BASE_URL}/api/financeiro/score-inadimplencia/localizacao`,
        {
          cliente_codigo: item.cliente_codigo,
          cidade,
          bairro,
          latitude,
          longitude,
        },
        // Mensagem de sucesso depende do corpo da resposta (`resolvido`),
        // então o toast automático (genérico) fica desligado aqui — quem
        // decide o texto certo é este componente, não o interceptor.
        { context: new HttpContext().set(TOAST_DESATIVADO, true) },
      )
      .subscribe({
        next: (localizacao) => {
          item.localizacao = localizacao;
          this.salvandoLocalizacao.set(false);
          this.clienteEmEdicao.set(null);
          this.toasts.sucesso(
            localizacao.resolvido
              ? 'Localização salva e usada no clima deste cliente.'
              : 'Localização salva, mas não conseguimos localizar — o clima segue pelo município.',
          );
        },
        error: (erro: HttpErrorResponse) => {
          const mensagem = mensagemErro(erro, 'Não foi possível salvar a localização.');
          this.erroLocalizacao.set(mensagem);
          this.toasts.erro(mensagem);
          this.salvandoLocalizacao.set(false);
        },
      });
  }
}
