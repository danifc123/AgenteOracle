import { Component, ElementRef, HostListener, ViewChild, computed, inject, input, model, signal } from '@angular/core';

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
  styleUrl: './select-busca.scss'
})
export class SelectBusca {
  private readonly elementRef = inject(ElementRef);

  @ViewChild('gatilho') private readonly gatilhoRef!: ElementRef<HTMLButtonElement>;

  opcoes = input.required<OpcaoSelectBusca[]>();
  placeholder = input('Selecione...');
  valor = model<string | null>(null);

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

  protected readonly rotuloSelecionado = computed(() => {
    const opcao = this.opcoes().find((item) => item.valor === this.valor());
    return opcao?.rotulo ?? '';
  });

  toggle(): void {
    if (this.aberto()) {
      this.aberto.set(false);
      return;
    }

    this.termo.set('');
    this.posicionarPainel();
    this.aberto.set(true);
  }

  selecionar(opcao: OpcaoSelectBusca): void {
    this.valor.set(opcao.valor);
    this.aberto.set(false);
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

  private posicionarPainel(): void {
    const retangulo = this.gatilhoRef.nativeElement.getBoundingClientRect();
    this.posicao.set({
      top: retangulo.bottom + 4,
      left: retangulo.left,
      largura: retangulo.width
    });
  }
}
