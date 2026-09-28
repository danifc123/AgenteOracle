import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { AuditoriaPainel } from '../componentes/auditoria-painel/auditoria-painel';
import { NotificacaoAnaliseCurriculo } from '../componentes/notificacao-analise-curriculo/notificacao-analise-curriculo';
import { NotificacaoAuditoria } from '../componentes/notificacao-auditoria/notificacao-auditoria';
import { NotificacaoChatFinanceiro } from '../componentes/notificacao-chat-financeiro/notificacao-chat-financeiro';
import { Sidebar } from '../componentes/sidebar/sidebar';
import { Toast } from '../componentes/toast/toast';

@Component({
  selector: 'app-layout',
  imports: [
    RouterOutlet,
    Sidebar,
    NotificacaoAuditoria,
    AuditoriaPainel,
    NotificacaoAnaliseCurriculo,
    NotificacaoChatFinanceiro,
    Toast,
  ],
  templateUrl: './layout.html',
  styleUrl: './layout.scss',
})
export class Layout {}
