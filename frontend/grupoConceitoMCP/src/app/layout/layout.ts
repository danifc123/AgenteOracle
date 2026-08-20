import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { AuditoriaPainel } from '../componentes/auditoria-painel/auditoria-painel';
import { NotificacaoAnaliseCurriculo } from '../componentes/notificacao-analise-curriculo/notificacao-analise-curriculo';
import { NotificacaoAuditoria } from '../componentes/notificacao-auditoria/notificacao-auditoria';
import { SeletorHomeDev } from '../componentes/seletor-home-dev/seletor-home-dev';
import { Sidebar } from '../componentes/sidebar/sidebar';
import { Toast } from '../componentes/toast/toast';

@Component({
  selector: 'app-layout',
  imports: [
    RouterOutlet,
    Sidebar,
    NotificacaoAuditoria,
    AuditoriaPainel,
    SeletorHomeDev,
    NotificacaoAnaliseCurriculo,
    Toast,
  ],
  templateUrl: './layout.html',
  styleUrl: './layout.scss',
})
export class Layout {}
