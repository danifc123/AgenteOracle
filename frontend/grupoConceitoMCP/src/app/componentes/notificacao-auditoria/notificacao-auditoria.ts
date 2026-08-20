import { Component, inject } from '@angular/core';
import { Auditoria } from '../../servicos/auditoria';

/** Sino único, fixo no canto superior direito do layout — só abre o painel
 * (`auditoria.abrir()`), nunca busca nada sozinho. Qual departamento é
 * auditado se decide DENTRO do painel (`auditoria-painel`), não aqui — um
 * sino por módulo já foi tentado e causou duplicação visual de notificação,
 * então a escolha de módulo virou um seletor dentro do dialog único. A
 * bolinha vermelha reflete o resultado da última execução manual desta
 * sessão (signal compartilhado com o painel via `Auditoria`); antes da
 * primeira execução, não há achado nenhum e a bolinha não aparece. */
@Component({
  selector: 'app-notificacao-auditoria',
  imports: [],
  templateUrl: './notificacao-auditoria.html',
  styleUrl: './notificacao-auditoria.scss',
})
export class NotificacaoAuditoria {
  protected readonly auditoria = inject(Auditoria);

  protected abrir(): void {
    this.auditoria.abrir();
  }
}
