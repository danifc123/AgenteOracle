import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { AuditoriaPainel } from '../componentes/auditoria-painel/auditoria-painel';
import { NotificacaoAuditoria } from '../componentes/notificacao-auditoria/notificacao-auditoria';
import { SeletorHomeDev } from '../componentes/seletor-home-dev/seletor-home-dev';
import { Sidebar } from '../componentes/sidebar/sidebar';

@Component({
  selector: 'app-layout',
  imports: [RouterOutlet, Sidebar, NotificacaoAuditoria, AuditoriaPainel, SeletorHomeDev],
  templateUrl: './layout.html',
  styleUrl: './layout.scss',
})
export class Layout {}
