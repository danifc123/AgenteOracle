import { Injectable, signal } from '@angular/core';

export type TipoToast = 'sucesso' | 'erro' | 'aviso';

export interface ToastItem {
  id: string;
  tipo: TipoToast;
  mensagem: string;
}

const DURACAO_MS = 5000;

/** Toast genérico — qualquer tela injeta este serviço e chama `sucesso()`/
 * `erro()`/`aviso()` ao terminar uma ação (salvar, excluir, etc.), sem
 * precisar de `erro` local nem de repetir a marcação visual em cada tela.
 * Exibido pelo `Toast` (componente montado uma vez em `layout.html`, igual
 * `NotificacaoAnaliseCurriculo` já faz pro caso específico de currículo). */
@Injectable({ providedIn: 'root' })
export class Toasts {
  private readonly _itens = signal<ToastItem[]>([]);
  readonly itens = this._itens.asReadonly();

  /** Ação terminou, mas com uma ressalva — não é falha (fica vermelho) nem
   * sucesso pleno (fica verde); tom âmbar próprio. */
  aviso(mensagem: string): void {
    this.mostrar('aviso', mensagem);
  }

  erro(mensagem: string): void {
    this.mostrar('erro', mensagem);
  }

  remover(id: string): void {
    this._itens.update((atual) => atual.filter((item) => item.id !== id));
  }

  sucesso(mensagem: string): void {
    this.mostrar('sucesso', mensagem);
  }

  private mostrar(tipo: TipoToast, mensagem: string): void {
    const id = crypto.randomUUID();
    this._itens.update((atual) => [...atual, { id, tipo, mensagem }]);
    setTimeout(() => this.remover(id), DURACAO_MS);
  }
}
