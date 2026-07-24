import { Routes } from '@angular/router';
import { Layout } from './layout/layout';
import { Home } from './pages/home/home';
import { Financeiro } from './pages/modulos/financeiro/financeiro';
import { CriarRelatorio } from './pages/modulos/financeiro/criar-relatorio/criar-relatorio';
import { Chat } from './pages/chat/chat';
import { Login } from './pages/login/login';
import { Historico } from './pages/relatorios/historico/historico';
import { Usuarios } from './pages/usuarios/usuarios';
import { adminGuard } from './servicos/admin.guard';
import { authGuard } from './servicos/auth.guard';

export const routes: Routes = [
  { path: 'login', component: Login },
  {
    path: '',
    component: Layout,
    canActivate: [authGuard],
    children: [
      { path: '', component: Home },
      { path: 'financeiro/criar-relatorio', component: CriarRelatorio },
      { path: 'financeiro/:moduloId', component: Financeiro },
      { path: 'chat', component: Chat },
      { path: 'relatorios/historico', component: Historico },
      { path: 'usuarios', component: Usuarios, canActivate: [adminGuard] }
    ]
  },
  { path: '**', redirectTo: '' }
];
