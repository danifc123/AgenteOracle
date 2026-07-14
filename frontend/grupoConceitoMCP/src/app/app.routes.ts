import { Routes } from '@angular/router';
import { Home } from './pages/home/home';
import { ModuloFinanceiro } from './pages/financeiro/modulo/modulo';
import { Chat } from './pages/chat/chat';
import { Historico } from './pages/relatorios/historico/historico';

export const routes: Routes = [
  { path: '', component: Home },
  { path: 'financeiro/:moduloId', component: ModuloFinanceiro },
  { path: 'chat', component: Chat },
  { path: 'relatorios/historico', component: Historico },
  { path: '**', redirectTo: '' }
];
