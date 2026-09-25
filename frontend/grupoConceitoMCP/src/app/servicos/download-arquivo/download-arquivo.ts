/** Nome do arquivo a partir do header `Content-Disposition` da resposta, ou
 * `nomePadrao` se o header não vier ou não tiver `filename`. */
export function extrairNomeArquivo(contentDisposition: string | null, nomePadrao: string): string {
  const match = contentDisposition?.match(/filename="?([^"]+)"?/);
  return match?.[1] ?? nomePadrao;
}

/** Dispara o download de um blob já recebido do backend (relatório, planilha
 * combinada, anexo do chat...) — cria um link temporário, clica nele e limpa
 * a URL do objeto na sequência. */
export function baixarBlob(blob: Blob, nomeArquivo: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = nomeArquivo;
  link.click();
  URL.revokeObjectURL(url);
}
