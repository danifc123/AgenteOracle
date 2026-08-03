import { Component, inject } from '@angular/core';
import { Auditoria } from '../../servicos/auditoria';

/** Sino fixo no canto superior direito do layout — só abre o painel
 * (`auditoria.abrir()`), nunca busca nada sozinho. A bolinha vermelha reflete
 * o resultado da última execução manual desta sessão (signal compartilhado
 * com o painel via `Auditoria`); antes da primeira execução, não há achado
 * nenhum e a bolinha simplesmente não aparece. */
@Component({
  selector: 'app-notificacao-auditoria',
  imports: [],
  templateUrl: './notificacao-auditoria.html',
  styleUrl: './notificacao-auditoria.scss'
})
export class NotificacaoAuditoria {
  protected readonly auditoria = inject(Auditoria);

  protected abrir(): void {
    this.auditoria.abrir();
  }
}
