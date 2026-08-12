import { Component, output, signal } from '@angular/core';

// ".doc" (formato binário antigo do Word) fica de fora — não existe
// biblioteca pura Python confiável pra extrair texto dele no backend
// (ver `tools/rh/extracao_curriculo.py`), então nem oferecemos aqui.
const EXTENSOES_ACEITAS = ['.pdf', '.docx'];

/** Seleção múltipla de currículos — o RH sobe vários de uma vez em
 * "Análise de Candidato" e cada um vira uma análise independente em
 * segundo plano (ver `servicos/analise-curriculo.ts`). */
@Component({
  selector: 'app-seletor-arquivo-curriculo',
  imports: [],
  templateUrl: './seletor-arquivo-curriculo.html',
  styleUrl: './seletor-arquivo-curriculo.scss',
})
export class SeletorArquivoCurriculo {
  arquivosAlterados = output<File[]>();

  protected readonly arquivos = signal<File[]>([]);
  protected readonly arrastandoSobre = signal(false);
  protected readonly erro = signal<string | null>(null);

  private adicionarArquivos(novos: File[]): void {
    if (!novos.length) {
      return;
    }
    const invalido = novos.some(
      (arquivo) => !EXTENSOES_ACEITAS.some((extensao) => arquivo.name.toLowerCase().endsWith(extensao)),
    );
    if (invalido) {
      this.erro.set('Selecione apenas arquivos .pdf ou .docx');
      return;
    }
    this.erro.set(null);
    this.arquivos.update((atual) => [...atual, ...novos]);
    this.arquivosAlterados.emit(this.arquivos());
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
    this.adicionarArquivos(Array.from(evento.dataTransfer?.files ?? []));
  }

  limparTudo(): void {
    this.arquivos.set([]);
    this.erro.set(null);
    this.arquivosAlterados.emit([]);
  }

  remover(arquivo: File): void {
    this.arquivos.update((atual) => atual.filter((item) => item !== arquivo));
    this.arquivosAlterados.emit(this.arquivos());
  }

  selecionarViaInput(evento: Event): void {
    const input = evento.target as HTMLInputElement;
    this.adicionarArquivos(Array.from(input.files ?? []));
    input.value = '';
  }

  protected tamanhoFormatado(arquivo: File): string {
    const kb = arquivo.size / 1024;
    return kb < 1024 ? `${kb.toFixed(0)} KB` : `${(kb / 1024).toFixed(1)} MB`;
  }
}
