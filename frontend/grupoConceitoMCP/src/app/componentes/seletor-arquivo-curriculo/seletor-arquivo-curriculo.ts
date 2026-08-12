import { Component, computed, output, signal } from '@angular/core';

const EXTENSOES_ACEITAS = ['.pdf', '.doc', '.docx'];

@Component({
  selector: 'app-seletor-arquivo-curriculo',
  imports: [],
  templateUrl: './seletor-arquivo-curriculo.html',
  styleUrl: './seletor-arquivo-curriculo.scss',
})
export class SeletorArquivoCurriculo {
  arquivoAlterado = output<File | null>();

  protected readonly arquivo = signal<File | null>(null);
  protected readonly arrastandoSobre = signal(false);
  protected readonly erro = signal<string | null>(null);

  protected readonly tamanhoFormatado = computed(() => {
    const arquivo = this.arquivo();
    if (!arquivo) {
      return '';
    }
    const kb = arquivo.size / 1024;
    return kb < 1024 ? `${kb.toFixed(0)} KB` : `${(kb / 1024).toFixed(1)} MB`;
  });

  private definirArquivo(arquivo: File | null): void {
    if (arquivo && !EXTENSOES_ACEITAS.some((extensao) => arquivo.name.toLowerCase().endsWith(extensao))) {
      this.erro.set('Selecione um arquivo .pdf, .doc ou .docx');
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
