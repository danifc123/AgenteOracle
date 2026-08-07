import { HttpErrorResponse } from '@angular/common/http';

/** Mensagem de erro vinda do backend (`{"erro": "..."}`), ou `mensagemPadrao`
 * se a resposta não tiver esse formato (erro de rede, servidor fora do ar). */
export function mensagemErro(erro: HttpErrorResponse, mensagemPadrao: string): string {
  return erro.error?.erro || mensagemPadrao;
}
