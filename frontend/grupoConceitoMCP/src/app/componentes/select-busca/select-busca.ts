import {
  Component,
  ElementRef,
  HostListener,
  ViewChild,
  computed,
  inject,
  input,
  model,
  signal,
} from '@angular/core';

export interface OpcaoSelectBusca {
  valor: string;
  rotulo: string;
}

interface PosicaoPainel {
  top: number;
  left: number;
  largura: number;
}

@Component({
  selector: 'app-select-busca',
  imports: [],
  templateUrl: './select-busca.html',
  styleUrl: './select-busca.scss',
})
export class SelectBusca {
  private readonly elementRef = inject(ElementRef);

  @ViewChild('gatilho') private readonly gatilhoRef!: ElementRef<HTMLButtonElement>;
  @ViewChild('painel') private readonly painelRef?: ElementRef<HTMLDivElement>;

  opcoes = input.required<OpcaoSelectBusca[]>();
  placeholder = input('Selecione...');
  multiplo = input(false);
  /** Label pequeno mostrado acima do campo, pra identificar o que ele espera mesmo depois de preenchido. */
  rotulo = input<string | null>(null);

  /** Usado quando multiplo() é false. */
  valor = model<string | null>(null);
  /** Usado quando multiplo() é true. */
  valores = model<string[]>([]);

  protected readonly aberto = signal(false);
  protected readonly termo = signal('');
  protected readonly posicao = signal<PosicaoPainel>({ top: 0, left: 0, largura: 0 });

  protected readonly opcoesFiltradas = computed(() => {
    const termo = this.termo().trim().toLowerCase();
    const opcoes = this.opcoes();

    if (!termo) {
      return opcoes;
    }

    return opcoes.filter((opcao) => opcao.rotulo.toLowerCase().includes(termo));
  });

  /** Só faz sentido em modo múltiplo — compara contra `opcoesFiltradas()`
   * (não `opcoes()` inteiro), então "marcar/desmarcar todos" age sobre o
   * que está visível na busca atual, mesmo padrão de outras listas com
   * filtro + seleção em massa. */
  protected readonly todosSelecionados = computed(() => {
    const filtradas = this.opcoesFiltradas();
    return filtradas.length > 0 && filtradas.every((opcao) => this.valores().includes(opcao.valor));
  });

  protected readonly temSelecao = computed(() => {
    return this.multiplo() ? this.valores().length > 0 : !!this.valor();
  });

  protected readonly rotuloSelecionado = computed(() => {
    if (this.multiplo()) {
      const selecionadas = this.valores();

      if (!selecionadas.length) {
        return '';
      }

      if (selecionadas.length === 1) {
        return (
          this.opcoes().find((item) => item.valor === selecionadas[0])?.rotulo ?? selecionadas[0]
        );
      }

      return `${selecionadas.length} selecionadas`;
    }

    const opcao = this.opcoes().find((item) => item.valor === this.valor());
    return opcao?.rotulo ?? '';
  });

  protected estaSelecionada(opcao: OpcaoSelectBusca): boolean {
    return this.multiplo() ? this.valores().includes(opcao.valor) : opcao.valor === this.valor();
  }

  /** Marca/desmarca de uma vez todas as opções que estão visíveis na busca
   * atual (`opcoesFiltradas()`) — opção escondida pelo filtro no momento
   * não é mexida, só as que aparecem na lista agora. */
  alternarTodos(): void {
    const filtradas = this.opcoesFiltradas().map((opcao) => opcao.valor);
    if (this.todosSelecionados()) {
      this.valores.update((atual) => atual.filter((valor) => !filtradas.includes(valor)));
    } else {
      this.valores.update((atual) => [...new Set([...atual, ...filtradas])]);
    }
  }

  limpar(evento: Event): void {
    evento.stopPropagation();

    if (this.multiplo()) {
      this.valores.set([]);
    } else {
      this.valor.set(null);
    }

    this.aberto.set(false);
  }

  selecionar(opcao: OpcaoSelectBusca): void {
    if (this.multiplo()) {
      const atual = this.valores();
      const novo = atual.includes(opcao.valor)
        ? atual.filter((valor) => valor !== opcao.valor)
        : [...atual, opcao.valor];
      this.valores.set(novo);
      return;
    }

    this.valor.set(opcao.valor);
    this.aberto.set(false);
  }

  toggle(): void {
    if (this.aberto()) {
      this.aberto.set(false);
      return;
    }

    this.termo.set('');
    this.posicionarPainel();
    this.aberto.set(true);
    requestAnimationFrame(() => this.ajustarDirecao());
  }

  @HostListener('document:click', ['$event'])
  aoClicarFora(event: MouseEvent): void {
    if (!this.elementRef.nativeElement.contains(event.target as Node)) {
      this.aberto.set(false);
    }
  }

  @HostListener('window:scroll')
  @HostListener('window:resize')
  aoRolarOuRedimensionar(): void {
    if (this.aberto()) {
      this.aberto.set(false);
    }
  }

  /** Depois que o painel é renderizado (e sua altura real é conhecida), inverte
   *  pra abrir para cima se não couber abaixo do gatilho mas couber acima. */
  private ajustarDirecao(): void {
    const painelEl = this.painelRef?.nativeElement;
    if (!painelEl) {
      return;
    }

    const retangulo = this.gatilhoRef.nativeElement.getBoundingClientRect();
    const alturaPainel = painelEl.offsetHeight;
    const espacoAbaixo = window.innerHeight - retangulo.bottom;
    const espacoAcima = retangulo.top;

    if (espacoAbaixo < alturaPainel + 4 && espacoAcima > espacoAbaixo) {
      this.posicao.set({
        top: Math.max(4, retangulo.top - alturaPainel - 4),
        left: retangulo.left,
        largura: retangulo.width,
      });
    }
  }

  private posicionarPainel(): void {
    const retangulo = this.gatilhoRef.nativeElement.getBoundingClientRect();
    this.posicao.set({
      top: retangulo.bottom + 4,
      left: retangulo.left,
      largura: retangulo.width,
    });
  }
}
