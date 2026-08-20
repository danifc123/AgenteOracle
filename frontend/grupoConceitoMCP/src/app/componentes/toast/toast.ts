import { Component, inject } from '@angular/core';
import { Toasts } from '../../servicos/toasts';

/** Empilha os toasts do serviço `Toasts` no canto inferior direito — montado
 * uma vez em `layout.html`, igual `NotificacaoAnaliseCurriculo`. Qualquer
 * tela injeta `Toasts` e chama `.sucesso()`/`.erro()` ao terminar uma ação;
 * este componente só desenha o que já está na fila. */
@Component({
  selector: 'app-toast',
  imports: [],
  templateUrl: './toast.html',
  styleUrl: './toast.scss',
})
export class Toast {
  protected readonly toasts = inject(Toasts);
}
