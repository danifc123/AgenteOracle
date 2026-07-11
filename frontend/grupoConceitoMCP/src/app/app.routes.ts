import { Routes } from '@angular/router';
import { Home } from './pages/home/home';
import { Transacoes } from './pages/financeiro/transacoes/transacoes';
import { Chat } from './pages/chat/chat';

export const routes: Routes = [
  { path: '', component: Home },
  { path: 'financeiro/transacoes', component: Transacoes },
  { path: 'chat', component: Chat },
  { path: '**', redirectTo: '' }
];
