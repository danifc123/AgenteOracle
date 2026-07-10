import { Routes } from '@angular/router';
import { Home } from './pages/home/home';
import { Transacoes } from './pages/financeiro/transacoes/transacoes';

export const routes: Routes = [
  { path: '', component: Home },
  { path: 'financeiro/transacoes', component: Transacoes },
  { path: '**', redirectTo: '' }
];
