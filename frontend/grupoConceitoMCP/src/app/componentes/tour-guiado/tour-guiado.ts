import {
  Component,
  DestroyRef,
  HostListener,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  untracked,
} from '@angular/core';
import { Botao } from '../botao/botao';

/** `alvo` é um seletor CSS (ex: `'[data-tour-alvo="nome"]'`) — o passo
 * aponta pra um elemento no template de QUEM USA o tour, não um filho do
 * próprio componente, por isso seletor e não `ViewChild`. */
export interface PassoTour {
  alvo: string;
  titulo: string;
  descricao: string;
}

interface PosicaoDestaque {
  top: number;
  left: number;
  width: number;
  height: number;
}

interface PosicaoBalao {
  top: number;
  left: number;
}

const RESPIRO_DESTAQUE = 8;
const ESPACO_BALAO = 16;
const LARGURA_BALAO = 320;
const ALTURA_BALAO_ESTIMADA = 200;
// Um pouco mais que `--duration-base` (200ms, ver styles.scss) pra garantir
// que a transição CSS termine antes da gente tirar a classe que a liga.
const DURACAO_TRANSICAO_MS = 220;

/** Tour guiado genérico (spotlight + balão), passo a passo — não sabe
 * NADA sobre o que está explicando, só entende "lista de passos, cada um
 * apontando pra um elemento na tela". Quem usa fornece `PassoTour[]` com
 * seletores CSS; este componente cuida só de destacar o alvo (mesma
 * técnica de posicionamento de `select-busca.ts`: `getBoundingClientRect`
 * + `requestAnimationFrame` em loop enquanto aberto) e navegar entre os
 * passos. Propositalmente sem saber de formulário, preço, provedor — é
 * o que permite reusar em qualquer outra tela do site depois, sem mexer
 * aqui de novo.
 *
 * Nunca preenche nem altera nada na tela por conta própria (é só
 * apontar + explicar) — se um passo aponta pra um elemento que não está
 * no DOM agora (ex: campo condicional escondido), esse passo é pulado
 * sozinho, na mesma direção da navegação. */
@Component({
  selector: 'app-tour-guiado',
  imports: [Botao],
  templateUrl: './tour-guiado.html',
  styleUrl: './tour-guiado.scss',
})
export class TourGuiado {
  passos = input.required<PassoTour[]>();
  aberto = input(false);

  fechar = output<void>();

  protected readonly passoIndice = signal(0);
  protected readonly destaque = signal<PosicaoDestaque | null>(null);
  protected readonly balao = signal<PosicaoBalao | null>(null);
  protected readonly balaoAcima = signal(false);

  protected readonly passoAtual = computed<PassoTour | null>(() => this.passos()[this.passoIndice()] ?? null);
  protected readonly ehPrimeiro = computed(() => this.passoIndice() === 0);
  protected readonly ehUltimo = computed(() => this.passoIndice() === this.passos().length - 1);

  /** `true` só durante a animação de "fechar" num alvo novo (pouco depois
   * de mudar de passo). O loop de `requestAnimationFrame` recalcula a
   * posição a cada quadro pra ACOMPANHAR rolagem/redimensionamento do
   * MESMO alvo — se a transição CSS ficasse ligada o tempo todo, cada um
   * desses recálculos (inclusive durante um scroll comum) reacionava a
   * animação, e o destaque ficava "correndo atrás" da rolagem em vez de
   * grudado nela. */
  protected readonly emTransicao = signal(false);

  private idQuadro: number | null = null;
  private idTransicao: ReturnType<typeof setTimeout> | null = null;

  constructor() {
    // `untracked` é essencial aqui: `garantirAlvoValido` lê `passoIndice`/
    // `passos` por baixo (via `passoAtual`), e `avancar()`/`voltar()`
    // escrevem em `passoIndice` fora deste effect — sem `untracked`, o
    // effect passaria a depender de `passoIndice` também, e cada avanço de
    // passo disparava o effect de novo, resetando `passoIndice` pra 0 na
    // hora (mesmo padrão já usado em `configuracoes-chamados.ts`).
    effect(() => {
      const estaAberto = this.aberto();
      untracked(() => {
        if (estaAberto) {
          this.passoIndice.set(0);
          this.garantirAlvoValido(1);
          this.iniciarAcompanhamento();
        } else {
          this.pararAcompanhamento();
        }
      });
    });
    // Sem isso, destruir o componente com o tour aberto (ex: navegar pra
    // outra rota no meio do tour) deixaria o loop de `requestAnimationFrame`
    // rodando pra sempre — `aberto()` nunca mais vira `false` pra parar
    // ele pelo caminho normal do effect acima.
    inject(DestroyRef).onDestroy(() => this.pararAcompanhamento());
  }

  @HostListener('document:keydown.escape')
  protected aoPressionarEsc(): void {
    if (this.aberto()) {
      this.fechar.emit();
    }
  }

  protected avancar(): void {
    if (this.ehUltimo()) {
      this.fechar.emit();
      return;
    }
    this.passoIndice.update((indice) => indice + 1);
    this.garantirAlvoValido(1);
  }

  protected voltar(): void {
    if (this.ehPrimeiro()) {
      return;
    }
    this.passoIndice.update((indice) => indice - 1);
    this.garantirAlvoValido(-1);
  }

  protected pular(): void {
    this.fechar.emit();
  }

  /** Se o alvo do passo atual não existir no DOM agora, pula
   * automaticamente na mesma direção — um passo nunca fica "flutuando"
   * sem nada pra apontar. Fecha o tour se não sobrar nenhum passo com
   * alvo válido nessa direção. */
  private garantirAlvoValido(direcao: 1 | -1): void {
    const total = this.passos().length;
    for (let tentativas = 0; tentativas < total; tentativas++) {
      const passo = this.passoAtual();
      if (!passo) {
        this.fechar.emit();
        return;
      }
      const alvo = this.buscarAlvo(passo);
      if (alvo) {
        // Recentraliza o alvo na tela a cada passo novo — sem isso, um
        // campo perto do fim de um diálogo rolável (ou fora da área
        // visível) deixa o balão cortado/fora da tela, e a pessoa precisa
        // rolar manualmente só pra ler o passo. `smooth` já respeita
        // "reduzir movimento" sozinho (navegadores tratam isso nativo).
        // `?.` porque o JSDOM dos testes não implementa `scrollIntoView`.
        alvo.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
        this.animarTransicaoDePasso();
        this.atualizarPosicoes();
        return;
      }
      const proximoIndice = this.passoIndice() + direcao;
      if (proximoIndice < 0 || proximoIndice >= total) {
        this.fechar.emit();
        return;
      }
      this.passoIndice.set(proximoIndice);
    }
    this.fechar.emit();
  }

  private buscarAlvo(passo: PassoTour): HTMLElement | null {
    const elemento = document.querySelector<HTMLElement>(passo.alvo);
    return elemento ? this.resolverElementoComCaixa(elemento) : null;
  }

  /** Componentes como `app-botao` usam `:host { display: contents }` pra
   * não interferir no layout do pai que os envolve — mas isso também faz
   * o host não gerar caixa própria, e `getBoundingClientRect()` nele
   * sempre volta zerado (o `data-tour-alvo` de um passo pode acabar
   * exatamente nesse host). Se o alvo encontrado não tem tamanho, desce
   * pro primeiro filho real, repetindo até achar uma caixa de verdade —
   * o mesmo problema pode se repetir em cadeia (ex: um `app-botao` que
   * por acaso é o único filho de outro `display: contents`). */
  private resolverElementoComCaixa(elemento: HTMLElement): HTMLElement {
    let atual = elemento;
    while (atual.children.length > 0) {
      const retangulo = atual.getBoundingClientRect();
      if (retangulo.width > 0 || retangulo.height > 0) {
        return atual;
      }
      atual = atual.children[0] as HTMLElement;
    }
    return atual;
  }

  private iniciarAcompanhamento(): void {
    const quadro = (): void => {
      if (!this.aberto()) {
        this.idQuadro = null;
        return;
      }
      this.atualizarPosicoes();
      this.idQuadro = requestAnimationFrame(quadro);
    };
    this.idQuadro = requestAnimationFrame(quadro);
  }

  private pararAcompanhamento(): void {
    if (this.idQuadro !== null) {
      cancelAnimationFrame(this.idQuadro);
      this.idQuadro = null;
    }
    if (this.idTransicao !== null) {
      clearTimeout(this.idTransicao);
      this.idTransicao = null;
    }
    this.emTransicao.set(false);
  }

  /** Liga a transição CSS só pelo tempo da animação de "fechar" no alvo
   * novo, e desliga sozinha depois — assim o acompanhamento contínuo do
   * mesmo alvo (rolagem, redimensionamento) fica instantâneo, sem "correr
   * atrás". */
  private animarTransicaoDePasso(): void {
    this.emTransicao.set(true);
    if (this.idTransicao !== null) {
      clearTimeout(this.idTransicao);
    }
    this.idTransicao = setTimeout(() => {
      this.emTransicao.set(false);
      this.idTransicao = null;
    }, DURACAO_TRANSICAO_MS);
  }

  private atualizarPosicoes(): void {
    const passo = this.passoAtual();
    if (!passo) {
      return;
    }
    const alvo = this.buscarAlvo(passo);
    if (!alvo) {
      return;
    }

    const retangulo = alvo.getBoundingClientRect();
    this.destaque.set({
      top: retangulo.top - RESPIRO_DESTAQUE,
      left: retangulo.left - RESPIRO_DESTAQUE,
      width: retangulo.width + RESPIRO_DESTAQUE * 2,
      height: retangulo.height + RESPIRO_DESTAQUE * 2,
    });

    const espacoAbaixo = window.innerHeight - retangulo.bottom;
    const espacoAcima = retangulo.top;
    const abrirAcima = espacoAbaixo < ALTURA_BALAO_ESTIMADA && espacoAcima > espacoAbaixo;
    this.balaoAcima.set(abrirAcima);
    this.balao.set({
      top: abrirAcima
        ? retangulo.top - RESPIRO_DESTAQUE - ESPACO_BALAO
        : retangulo.bottom + RESPIRO_DESTAQUE + ESPACO_BALAO,
      left: Math.min(Math.max(16, retangulo.left), window.innerWidth - LARGURA_BALAO - 16),
    });
  }
}
