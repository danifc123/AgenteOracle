import { Component, computed, input, output, signal } from '@angular/core';
import { formatarTamanhoArquivo } from '../../servicos/formatar-tamanho-arquivo';

export type CorSeletorArquivo = 'verde' | 'laranja';

@Component({
  selector: 'app-seletor-arquivo-excel',
  imports: [],
  templateUrl: './seletor-arquivo-excel.html',
  styleUrl: './seletor-arquivo-excel.scss',
})
export class SeletorArquivoExcel {
  rotulo = input.required<string>();
  cor = input<CorSeletorArquivo>('verde');

  arquivoAlterado = output<File | null>();

  protected readonly arquivo = signal<File | null>(null);
  protected readonly arrastandoSobre = signal(false);
  protected readonly erro = signal<string | null>(null);

  protected readonly tamanhoFormatado = computed(() => {
    const arquivo = this.arquivo();
    return arquivo ? formatarTamanhoArquivo(arquivo.size) : '';
  });

  private definirArquivo(arquivo: File | null): void {
    if (arquivo && !arquivo.name.toLowerCase().endsWith('.xlsx')) {
      this.erro.set('Selecione um arquivo .xlsx');
      return;
    }
    this.erro.set(null);
    this.arquivo.set(arquivo);
    this.arquivoAlterado.emit(arquivo);
  }

  aoArrastarSobre(evento: DragEvent): void {
    evento.preventDefault();
    this.arrastandoSobre.set(true);
  }

  aoSairArraste(): void {
    this.arrastandoSobre.set(false);
  }

  aoSoltarArquivo(evento: DragEvent): void {
    evento.preventDefault();
    this.arrastandoSobre.set(false);
    this.definirArquivo(evento.dataTransfer?.files?.[0] ?? null);
  }

  remover(): void {
    this.definirArquivo(null);
  }

  selecionarViaInput(evento: Event): void {
    const input = evento.target as HTMLInputElement;
    this.definirArquivo(input.files?.[0] ?? null);
    input.value = '';
  }
}
