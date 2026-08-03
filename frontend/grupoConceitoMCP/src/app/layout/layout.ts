import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { AuditoriaPainel } from '../componentes/auditoria-painel/auditoria-painel';
import { NotificacaoAuditoria } from '../componentes/notificacao-auditoria/notificacao-auditoria';
import { Sidebar } from '../componentes/sidebar/sidebar';

@Component({
  selector: 'app-layout',
  imports: [RouterOutlet, Sidebar, NotificacaoAuditoria, AuditoriaPainel],
  templateUrl: './layout.html',
  styleUrl: './layout.scss'
})
export class Layout {}
