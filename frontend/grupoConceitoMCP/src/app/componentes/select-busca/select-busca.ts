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

  // Enquanto o painel está aberto, acompanha a posição do gatilho a cada
  // frame — sem isso, o painel (`position: fixed`, coordenadas calculadas
  // só na abertura) fica "preso" na posição antiga quando o layout muda por
  // outro motivo que não scroll/resize da janela (ex: marcar um papel de TI
  // faz aparecer campo novo embaixo no mesmo diálogo, empurrando o resto do
  // formulário sem disparar scroll/resize nenhum).
  private idAcompanhamento: number | null = null;

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

    this.fechar();
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
    this.fechar();
  }

  toggle(): void {
    if (this.aberto()) {
      this.fechar();
      return;
    }

    this.termo.set('');
    this.atualizarPosicao();
    this.aberto.set(true);
    this.iniciarAcompanhamento();
  }

  @HostListener('document:click', ['$event'])
  aoClicarFora(event: MouseEvent): void {
    if (!this.elementRef.nativeElement.contains(event.target as Node)) {
      this.fechar();
    }
  }

  @HostListener('window:scroll')
  @HostListener('window:resize')
  aoRolarOuRedimensionar(): void {
    this.fechar();
  }

  private fechar(): void {
    this.aberto.set(false);
    if (this.idAcompanhamento !== null) {
      cancelAnimationFrame(this.idAcompanhamento);
      this.idAcompanhamento = null;
    }
  }

  /** Reposiciona a cada frame enquanto o painel estiver aberto — pára
   * sozinho (não agenda o próximo frame) assim que `aberto()` virar false,
   * seja por `fechar()` ou por qualquer outro caminho que zere o signal. */
  private iniciarAcompanhamento(): void {
    const passo = (): void => {
      if (!this.aberto()) {
        this.idAcompanhamento = null;
        return;
      }
      this.atualizarPosicao();
      this.idAcompanhamento = requestAnimationFrame(passo);
    };
    this.idAcompanhamento = requestAnimationFrame(passo);
  }

  /** Recalcula a posição do painel a partir do gatilho AGORA — usada tanto
   * na abertura quanto em todo frame de `iniciarAcompanhamento()`. Abre pra
   * cima só quando não há espaço embaixo mas há espaço de sobra acima
   * (altura real do painel, já renderizado — por isso o primeiro frame
   * ainda pode abrir pra baixo e corrigir no seguinte, imperceptível). */
  private atualizarPosicao(): void {
    const retangulo = this.gatilhoRef.nativeElement.getBoundingClientRect();
    const alturaPainel = this.painelRef?.nativeElement.offsetHeight ?? 0;
    const espacoAbaixo = window.innerHeight - retangulo.bottom;
    const espacoAcima = retangulo.top;
    const abrirParaCima = alturaPainel > 0 && espacoAbaixo < alturaPainel + 4 && espacoAcima > espacoAbaixo;

    this.posicao.set({
      top: abrirParaCima ? Math.max(4, retangulo.top - alturaPainel - 4) : retangulo.bottom + 4,
      left: retangulo.left,
      largura: retangulo.width,
    });
  }
}
