import { Component, ElementRef, ViewChild, computed, input, signal } from '@angular/core';
import { formatarMoedaAbreviada } from '../../utilitarios/formatacao-moeda';

export interface PontoSerie {
  rotulo: string;
  valor: number;
}

export interface SerieGrafico {
  nome: string;
  cor: string;
  pontos: PontoSerie[];
  /** Mesma cor/identidade da série, só o traço muda (ex: projeção que continua o histórico). */
  tracejada?: boolean;
  /** Em gráficos de barra, desenha essa série como linha por cima das
   * barras em vez de virar mais um grupo de barra (ex: total estimado
   * sobreposto ao confirmado). Sem efeito em gráficos de linha. */
  linhaSobreposta?: boolean;
}

interface PontoXY {
  x: number;
  y: number;
  valor: number;
}

interface LinhaDesenhada {
  nome: string;
  cor: string;
  tracejada: boolean;
  path: string;
  pontos: PontoXY[];
  apagada: boolean;
}

interface BarraDesenhada {
  nome: string;
  cor: string;
  x: number;
  y: number;
  largura: number;
  altura: number;
  valor: number;
  apagada: boolean;
}

interface GrupoBarras {
  rotulo: string;
  x: number;
  barras: BarraDesenhada[];
}

interface LinhaGrade {
  y: number;
  rotulo: string;
}

interface Tooltip {
  x: number;
  rotulo: string;
  itens: { nome: string; cor: string; valor: number }[];
  caixaX: number;
  caixaY: number;
  caixaLargura: number;
  caixaAltura: number;
  /** Só existe no modo barra — a setinha que liga o balão até o topo da
   * coluna mais alta daquele mês, pra parecer que a informação "sai" da
   * coluna em vez de flutuar solta no gráfico. */
  seta: { pontos: string } | null;
}

const LARGURA_TOOLTIP = 148;
const ALTURA_LINHA_TOOLTIP = 16;

const LARGURA = 640;
const ALTURA = 260;
const MARGEM_ESQUERDA = 56;
const MARGEM_DIREITA = 12;
const MARGEM_SUPERIOR = 16;
const MARGEM_INFERIOR = 30;
const LARGURA_PLOT = LARGURA - MARGEM_ESQUERDA - MARGEM_DIREITA;
const ALTURA_PLOT = ALTURA - MARGEM_SUPERIOR - MARGEM_INFERIOR;

const MESES_ABREVIADOS = [
  'jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'
];

function formatarRotuloMes(rotulo: string): string {
  const match = /^(\d{4})-(\d{2})$/.exec(rotulo);
  if (!match) {
    return rotulo === 'vencido' ? 'Vencido' : rotulo;
  }
  const [, ano, mes] = match;
  return `${MESES_ABREVIADOS[Number(mes) - 1]}/${ano.slice(2)}`;
}

@Component({
  selector: 'app-grafico-serie',
  imports: [],
  templateUrl: './grafico-serie.html',
  styleUrl: './grafico-serie.scss'
})
export class GraficoSerie {
  @ViewChild('svgEl') private readonly svgRef?: ElementRef<SVGSVGElement>;

  tipo = input<'linha' | 'barra'>('linha');
  series = input.required<SerieGrafico[]>();

  protected readonly LARGURA = LARGURA;
  protected readonly ALTURA = ALTURA;
  protected readonly MARGEM_ESQUERDA = MARGEM_ESQUERDA;
  protected readonly MARGEM_DIREITA = MARGEM_DIREITA;

  protected readonly indiceHover = signal<number | null>(null);
  /** Nome da série sob o mouse (barra, linha/ponto ou item da legenda) —
   * usado só pra destacar essa série e apagar as outras, interação separada
   * do crosshair/tooltip por posição (`indiceHover`). */
  protected readonly serieEmDestaque = signal<string | null>(null);

  /** Eixo X = união (em ordem de primeira aparição) dos rótulos de todas as
   * séries — não dá pra assumir que a primeira série cobre todos os meses:
   * o histórico de vendas e a projeção, por exemplo, são séries diferentes
   * com timelines que só se encontram no mês de virada. */
  protected readonly rotulos = computed(() => {
    const vistos = new Set<string>();
    const rotulos: string[] = [];
    for (const serie of this.series()) {
      for (const ponto of serie.pontos) {
        if (!vistos.has(ponto.rotulo)) {
          vistos.add(ponto.rotulo);
          rotulos.push(ponto.rotulo);
        }
      }
    }
    return rotulos;
  });

  private readonly indicePorRotulo = computed(() => {
    const mapa = new Map<string, number>();
    this.rotulos().forEach((rotulo, indice) => mapa.set(rotulo, indice));
    return mapa;
  });

  protected readonly valorMaximo = computed(() => {
    const valores = this.series().flatMap((serie) => serie.pontos.map((ponto) => ponto.valor));
    const maximo = Math.max(0, ...valores);
    return maximo > 0 ? maximo * 1.15 : 1;
  });

  protected readonly grades = computed<LinhaGrade[]>(() => {
    const maximo = this.valorMaximo();
    return [0, 0.25, 0.5, 0.75, 1].map((fracao) => ({
      y: MARGEM_SUPERIOR + ALTURA_PLOT * (1 - fracao),
      rotulo: formatarMoedaAbreviada(maximo * fracao)
    }));
  });

  private readonly xPorIndice = computed(() => {
    const total = this.rotulos().length;
    if (total <= 1) {
      return [MARGEM_ESQUERDA + LARGURA_PLOT / 2];
    }
    const passo = LARGURA_PLOT / (total - 1);
    return Array.from({ length: total }, (_, indice) => MARGEM_ESQUERDA + indice * passo);
  });

  protected readonly rotulosEixoX = computed(() =>
    this.rotulos().map((rotulo, indice) => ({
      x: this.xPorIndice()[indice],
      texto: formatarRotuloMes(rotulo)
    }))
  );

  private y(valor: number): number {
    const maximo = this.valorMaximo();
    return MARGEM_SUPERIOR + ALTURA_PLOT * (1 - valor / maximo);
  }

  protected readonly linhas = computed<LinhaDesenhada[]>(() => {
    const seriesParaLinha =
      this.tipo() === 'barra' ? this.series().filter((serie) => serie.linhaSobreposta) : this.series();
    if (!seriesParaLinha.length) {
      return [];
    }
    const xs = this.xPorIndice();
    const indices = this.indicePorRotulo();
    const destaque = this.serieEmDestaque();
    return seriesParaLinha.map((serie) => {
      const pontos: PontoXY[] = serie.pontos.map((ponto) => ({
        x: xs[indices.get(ponto.rotulo) ?? 0],
        y: this.y(ponto.valor),
        valor: ponto.valor
      }));
      const path = pontos.map((ponto, indice) => `${indice === 0 ? 'M' : 'L'} ${ponto.x},${ponto.y}`).join(' ');
      return {
        nome: serie.nome,
        cor: serie.cor,
        tracejada: !!serie.tracejada,
        path,
        pontos,
        apagada: destaque !== null && destaque !== serie.nome
      };
    });
  });

  protected readonly grupos = computed<GrupoBarras[]>(() => {
    if (this.tipo() !== 'barra') {
      return [];
    }
    const series = this.series().filter((serie) => !serie.linhaSobreposta);
    const rotulos = this.rotulos();
    const totalGrupos = rotulos.length || 1;
    const larguraGrupo = LARGURA_PLOT / totalGrupos;
    const totalSeries = series.length || 1;
    const larguraBarra = (larguraGrupo * 0.6) / totalSeries;
    const espacamentoBarra = larguraBarra * 0.15;

    const valorPorRotulo = series.map((serie) => new Map(serie.pontos.map((ponto) => [ponto.rotulo, ponto.valor])));
    const destaque = this.serieEmDestaque();

    return rotulos.map((rotulo, indiceGrupo) => {
      const centroGrupo = MARGEM_ESQUERDA + larguraGrupo * (indiceGrupo + 0.5);
      const inicioGrupo = centroGrupo - (larguraBarra + espacamentoBarra) * (totalSeries / 2);

      const barras: BarraDesenhada[] = series.map((serie, indiceSerie) => {
        const valor = valorPorRotulo[indiceSerie].get(rotulo) ?? 0;
        const yTopo = this.y(valor);
        return {
          nome: serie.nome,
          cor: serie.cor,
          x: inicioGrupo + indiceSerie * (larguraBarra + espacamentoBarra),
          y: yTopo,
          largura: larguraBarra,
          altura: MARGEM_SUPERIOR + ALTURA_PLOT - yTopo,
          valor,
          apagada: destaque !== null && destaque !== serie.nome
        };
      });

      return { rotulo, x: centroGrupo, barras };
    });
  });

  protected readonly tooltip = computed<Tooltip | null>(() => {
    const indice = this.indiceHover();
    if (indice === null) {
      return null;
    }
    const rotulos = this.rotulos();
    const rotulo = rotulos[indice];
    if (rotulo === undefined) {
      return null;
    }
    const x = this.xPorIndice()[indice];
    // Séries com timelines diferentes (ex: histórico vs projeção) podem não
    // ter ponto nesse mês — omite da tooltip em vez de fingir um valor 0.
    const itens = this.series()
      .map((serie) => ({ nome: serie.nome, cor: serie.cor, ponto: serie.pontos.find((p) => p.rotulo === rotulo) }))
      .filter((item): item is { nome: string; cor: string; ponto: PontoSerie } => !!item.ponto)
      .map((item) => ({ nome: item.nome, cor: item.cor, valor: item.ponto.valor }));
    const caixaAltura = ALTURA_LINHA_TOOLTIP * (itens.length + 1) + 8;
    const caixaLargura = LARGURA_TOOLTIP;

    let caixaX: number;
    let caixaY: number;
    let seta: { pontos: string } | null = null;

    if (this.tipo() === 'barra') {
      // No modo barra o balão "sai" de cima da coluna mais alta daquele mês
      // (centralizado nela, só deslizando pra não estourar a borda do
      // gráfico) em vez de flutuar numa altura fixa desconectada das colunas.
      const grupo = this.grupos()[indice];
      const topoColunas = grupo?.barras.length
        ? Math.min(...grupo.barras.map((barra) => barra.y))
        : MARGEM_SUPERIOR + ALTURA_PLOT;
      const GAP_SETA = 8;

      caixaX = Math.min(Math.max(x - caixaLargura / 2, MARGEM_ESQUERDA), LARGURA - MARGEM_DIREITA - caixaLargura);
      caixaY = Math.max(MARGEM_SUPERIOR + 4, topoColunas - caixaAltura - GAP_SETA);

      const baseY = caixaY + caixaAltura;
      const pontaY = Math.max(baseY, topoColunas - 2);
      seta = { pontos: `${x - 7},${baseY} ${x + 7},${baseY} ${x},${pontaY}` };
    } else {
      const caixaNaDireita = x < MARGEM_ESQUERDA + LARGURA_PLOT * 0.6;
      caixaX = caixaNaDireita ? x + 10 : x - caixaLargura - 10;
      caixaY = MARGEM_SUPERIOR + 4;
    }

    return {
      x,
      rotulo: formatarRotuloMes(rotulo),
      itens,
      caixaX,
      caixaY,
      caixaLargura,
      caixaAltura,
      seta
    };
  });

  protected formatarValor(valor: number): string {
    return formatarMoedaAbreviada(valor);
  }

  protected aoMoverMouse(evento: MouseEvent): void {
    const svg = this.svgRef?.nativeElement;
    if (!svg) {
      return;
    }
    const ctm = svg.getScreenCTM();
    if (!ctm) {
      return;
    }
    const ponto = svg.createSVGPoint();
    ponto.x = evento.clientX;
    ponto.y = evento.clientY;
    const { x } = ponto.matrixTransform(ctm.inverse());

    const xs = this.xPorIndice();
    let indiceMaisProximo = 0;
    let menorDistancia = Infinity;
    xs.forEach((posicao, indice) => {
      const distancia = Math.abs(posicao - x);
      if (distancia < menorDistancia) {
        menorDistancia = distancia;
        indiceMaisProximo = indice;
      }
    });
    this.indiceHover.set(indiceMaisProximo);
  }

  protected aoSairMouse(): void {
    this.indiceHover.set(null);
  }

  protected aoPassarMouseNaSerie(nome: string): void {
    this.serieEmDestaque.set(nome);
  }

  protected aoSairDaSerie(): void {
    this.serieEmDestaque.set(null);
  }
}
