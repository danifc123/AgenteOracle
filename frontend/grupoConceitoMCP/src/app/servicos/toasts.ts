import { Injectable, signal } from '@angular/core';

export type TipoToast = 'sucesso' | 'erro';

export interface ToastItem {
  id: string;
  tipo: TipoToast;
  mensagem: string;
}

const DURACAO_MS = 5000;

/** Toast genérico — qualquer tela injeta este serviço e chama `sucesso()`/
 * `erro()` ao terminar uma ação (salvar, excluir, etc.), sem precisar de
 * `erro` local nem de repetir a marcação visual em cada tela. Exibido pelo
 * `Toast` (componente montado uma vez em `layout.html`, igual
 * `NotificacaoAnaliseCurriculo` já faz pro caso específico de currículo). */
@Injectable({ providedIn: 'root' })
export class Toasts {
  private readonly _itens = signal<ToastItem[]>([]);
  readonly itens = this._itens.asReadonly();

  sucesso(mensagem: string): void {
    this.mostrar('sucesso', mensagem);
  }

  erro(mensagem: string): void {
    this.mostrar('erro', mensagem);
  }

  remover(id: string): void {
    this._itens.update((atual) => atual.filter((item) => item.id !== id));
  }

  private mostrar(tipo: TipoToast, mensagem: string): void {
    const id = crypto.randomUUID();
    this._itens.update((atual) => [...atual, { id, tipo, mensagem }]);
    setTimeout(() => this.remover(id), DURACAO_MS);
  }
}
