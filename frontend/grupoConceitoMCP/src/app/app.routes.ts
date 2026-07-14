import { Routes } from '@angular/router';
import { Home } from './pages/home/home';
import { Financeiro } from './pages/modulos/financeiro/financeiro';
import { Chat } from './pages/chat/chat';
import { Historico } from './pages/relatorios/historico/historico';

export const routes: Routes = [
  { path: '', component: Home },
  { path: 'financeiro/:moduloId', component: Financeiro },
  { path: 'chat', component: Chat },
  { path: 'relatorios/historico', component: Historico },
  { path: '**', redirectTo: '' }
];
