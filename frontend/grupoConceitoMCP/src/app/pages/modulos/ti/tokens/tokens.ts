import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, effect, inject, signal } from '@angular/core';
import { Botao } from '../../../../componentes/botao/botao';
import { CampoNumerico } from '../../../../componentes/campo-numerico/campo-numerico';
import { Dialog } from '../../../../componentes/dialog/dialog';
import { EstadoVazio } from '../../../../componentes/estado-vazio/estado-vazio';
import { FatiaRosca, GraficoRosca } from '../../../../componentes/grafico-rosca/grafico-rosca';
import { GraficoSerie, SerieGrafico } from '../../../../componentes/grafico-serie/grafico-serie';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';
import { Selo } from '../../../../componentes/selo/selo';
import {
  AlteracoesConfiguracoesTi,
  ConfiguracoesTi,
} from '../../../../servicos/configuracoes-ti/configuracoes-ti';
import { mensagemErro } from '../../../../servicos/mensagens-erro/mensagens-erro';
import { UsoIa } from '../../../../servicos/uso-ia/uso-ia';

/** Cores reais do design system (ver `styles.scss`) — o nome do provedor
 * agora é o nome cadastrado por quem usa (`/ti/provedores`), não um código
 * fixo, então não dá mais pra fixar cor por provedor conhecido: roda por
 * essa lista, sempre na mesma ordem em que os provedores aparecem. */
const CORES_RESERVA = ['#1b4332', '#e8871e', '#2f9e58', '#5b6b62', '#c96f12'];

function corDoProvedor(indice: number): string {
  return CORES_RESERVA[indice % CORES_RESERVA.length];
}

/** "dd/MM" — mais curto que a data ISO completa, cabe no eixo X do
 * gráfico sem precisar mexer em `GraficoSerie` (que hoje só sabe formatar
 * rótulo no formato "YYYY-MM", pensado pra série mensal financeira). */
function formatarDiaCurto(dataIso: string): string {
  const partes = dataIso.split('-');
  return partes.length === 3 ? `${partes[2]}/${partes[1]}` : dataIso;
}

/** `custo` é sempre o preço CADASTRADO HOJE (não congelado por chamada) —
 * ver `server/ti/uso_ia.py::_custo_e_moeda` no backend. Até 4 casas: preço
 * por 1k tokens costuma ser bem pequeno (ex: R$ 0,0100), 2 casas some o
 * valor real. */
function formatarCusto(custo: number, moeda: string): string {
  return `${moeda} ${custo.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}`;
}

/** MÓDULO TI — TELA "TOKENS" (2026-09, redesenhada a partir do feedback:
 * "tudo virou cartão de KPI, quero mais intuitivo")
 *
 * O teto saiu do corpo da página pra um diálogo atrás da engrenagem no
 * cabeçalho — mesmo padrão que `chamados.html` já usa pras próprias
 * configurações (`configuracoesAbertas` + `app-dialog`). No lugar dos
 * cartões de "Chamadas (30 dias)"/"Tokens (30 dias)", que eram só números
 * soltos sem contexto, entram dois gráficos que já existiam no projeto
 * (`GraficoRosca`/`GraficoSerie`, usados em Estoque/Financeiro, nenhuma
 * lib nova) — donut de consumo por provedor e tendência diária. A tabela
 * continua: gráfico dá a intuição, tabela dá o número exato.
 *
 * Só desenvolvedor acessa (rota protegida por `devGuard`, item do menu
 * escondido de quem não é desenvolvedor via `ItemMenu.soDev`) — o backend
 * (`GET /api/ti/uso-ia`) também exige isso, então não é proteção só de
 * aparência. */
@Component({
  selector: 'app-tokens-ti',
  imports: [Botao, CampoNumerico, Dialog, EstadoVazio, GraficoRosca, GraficoSerie, ModuloHeader, Selo],
  templateUrl: './tokens.html',
  styleUrl: './tokens.scss',
})
export class Tokens {
  private readonly usoIa = inject(UsoIa);
  protected readonly configuracoes = inject(ConfiguracoesTi);

  protected readonly consumo = this.usoIa.consumo;
  protected readonly porUsuario = this.usoIa.porUsuario;
  protected readonly porDia = this.usoIa.porDia;
  protected readonly tokensHojePorDominio = this.usoIa.tokensHojePorDominio;

  /** "Geral" = por provedor/modelo (responde "o que está custando");
   * "usuario" = por pessoa (responde "quem está gastando"). */
  protected readonly abaAtiva = signal<'geral' | 'usuario'>('geral');

  protected readonly configuracoesAbertas = signal(false);
  protected readonly tetoTexto = signal('0');
  protected readonly salvandoTeto = signal(false);
  protected readonly erroTeto = signal<string | null>(null);

  protected readonly tokensHojeTotal = computed(() =>
    Object.values(this.tokensHojePorDominio()).reduce((total, valor) => total + valor, 0),
  );

  protected readonly fatiasProvedor = computed<FatiaRosca[]>(() => {
    const porProvedor = new Map<string, number>();
    for (const linha of this.consumo()) {
      porProvedor.set(linha.provedor, (porProvedor.get(linha.provedor) ?? 0) + linha.tokens_total);
    }
    return Array.from(porProvedor.entries()).map(([provedor, tokens], indice) => ({
      nome: provedor,
      valor: tokens,
      cor: corDoProvedor(indice),
    }));
  });

  protected readonly serieTokensPorDia = computed<SerieGrafico[]>(() => [
    {
      nome: 'Tokens',
      cor: '#1b4332',
      pontos: this.porDia().map((linha) => ({
        rotulo: formatarDiaCurto(linha.data),
        valor: linha.tokens_total,
      })),
    },
  ]);

  protected readonly tetoValido = computed<number | null>(() => {
    const numero = Number(this.tetoTexto());
    return Number.isInteger(numero) && numero >= 0 ? numero : null;
  });

  /** `null` = sem teto configurado (0), não mostra a barra de progresso. */
  protected readonly percentualTeto = computed<number | null>(() => {
    const teto = this.configuracoes.tetoTokensDiario();
    if (teto <= 0) {
      return null;
    }
    return Math.min(100, Math.round((this.tokensHojeTotal() / teto) * 100));
  });

  protected readonly tomTeto = computed<'ok' | 'atencao' | 'erro'>(() => {
    const percentual = this.percentualTeto();
    if (percentual === null) {
      return 'ok';
    }
    return percentual >= 100 ? 'erro' : percentual >= 80 ? 'atencao' : 'ok';
  });

  constructor() {
    this.usoIa.carregar();
    this.configuracoes.carregar();
    // Semeia o rascunho do teto sempre que o valor real do servidor muda
    // (primeiro load, e depois de salvar) — mesmo espírito de
    // `iniciarRascunho` em `configuracoes-chamados.ts`.
    effect(() => this.tetoTexto.set(String(this.configuracoes.tetoTokensDiario())));
  }

  protected rotuloCusto(custo: number | null, moeda: string | null): string {
    return custo !== null && moeda !== null ? formatarCusto(custo, moeda) : '—';
  }

  protected salvarTeto(): void {
    const teto = this.tetoValido();
    if (teto === null || this.salvandoTeto()) {
      return;
    }

    this.salvandoTeto.set(true);
    this.erroTeto.set(null);
    const alteracoes: AlteracoesConfiguracoesTi = { teto_tokens_diario: teto };
    this.configuracoes.salvar(alteracoes).subscribe({
      next: () => {
        this.salvandoTeto.set(false);
        this.configuracoesAbertas.set(false);
      },
      error: (erro: HttpErrorResponse) => {
        this.erroTeto.set(mensagemErro(erro, 'Não foi possível salvar o teto de tokens.'));
        this.salvandoTeto.set(false);
      },
    });
  }
}
