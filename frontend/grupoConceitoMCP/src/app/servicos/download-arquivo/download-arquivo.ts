import { Injectable, inject } from '@angular/core';
import { Toasts } from '../toasts/toasts';

/** Nome do arquivo a partir do header `Content-Disposition` da resposta, ou
 * `nomePadrao` se o header não vier ou não tiver `filename`. */
export function extrairNomeArquivo(contentDisposition: string | null, nomePadrao: string): string {
  const match = contentDisposition?.match(/filename="?([^"]+)"?/);
  return match?.[1] ?? nomePadrao;
}

const AVISO_AREA_DE_TRABALHO =
  'Evite salvar este arquivo na Área de Trabalho — ela sincroniza automaticamente com o OneDrive e costuma lotar o armazenamento. Salve em outra pasta (ex: Documentos ou uma pasta de rede).';

/** Dispara o download de um blob já recebido do backend (relatório, planilha
 * combinada, currículo, anexo do chat...) — cria um link temporário, clica
 * nele e limpa a URL do objeto na sequência. Serviço (não mais função livre)
 * porque também avisa sobre a Área de Trabalho a cada download — precisa do
 * `Toasts` injetado, e alguns dos 6 pontos que chamam isso rodam dentro de
 * callback de `subscribe()` (fora do contexto síncrono de injeção, onde
 * `inject()` solto quebraria). Aviso vale pra QUALQUER download do sistema
 * (antes só aparecia numa seção fixa da Home, só pra quem tinha o módulo
 * Financeiro — o conselho não é específico de Financeiro, é de qualquer
 * arquivo baixado, então faz mais sentido centralizado aqui). */
@Injectable({ providedIn: 'root' })
export class DownloadArquivo {
  private readonly toasts = inject(Toasts);

  baixar(blob: Blob, nomeArquivo: string): void {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = nomeArquivo;
    link.click();
    URL.revokeObjectURL(url);
    this.toasts.aviso(AVISO_AREA_DE_TRABALHO);
  }
}
