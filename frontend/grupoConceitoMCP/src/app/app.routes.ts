import { Routes } from '@angular/router';
import { Layout } from './layout/layout';
import { HomeRoteador } from './pages/home-roteador/home-roteador';
import { Financeiro } from './pages/modulos/financeiro/financeiro';
import { CriarRelatorio } from './pages/modulos/financeiro/criar-relatorio/criar-relatorio';
import { FluxoCaixa } from './pages/modulos/financeiro/fluxo-caixa/fluxo-caixa';
import { Vendas } from './pages/modulos/financeiro/vendas/vendas';
import { Estoque } from './pages/modulos/estoque/estoque';
import { EstoqueCriarRelatorio } from './pages/modulos/estoque/criar-relatorio/criar-relatorio';
import { EstoqueEspecificoGrupoConceito } from './pages/modulos/estoque/especifico-grupo-conceito/especifico-grupo-conceito';
import { EstoqueChat } from './pages/modulos/estoque/chat/estoque-chat';
import { Chat } from './pages/modulos/financeiro/chat/chat';
import { AnaliseCandidato } from './pages/modulos/rh/analise-candidato/analise-candidato';
import { Colaboradores } from './pages/modulos/rh/colaboradores/colaboradores';
import { Repescagem } from './pages/modulos/rh/repescagem/repescagem';
import { SelecionarCandidato } from './pages/modulos/rh/selecionar-candidato/selecionar-candidato';
import { SegurancaTi } from './pages/modulos/ti/seguranca/seguranca';
import { Login } from './pages/login/login';
import { AuditoriaHistorico } from './pages/auditoria/historico/auditoria-historico';
import { JuntarExcel } from './pages/juntar-excel/juntar-excel';
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
      { path: '', component: HomeRoteador },
      { path: 'financeiro/criar-relatorio', component: CriarRelatorio },
      { path: 'financeiro/fluxo-caixa', component: FluxoCaixa },
      { path: 'financeiro/vendas', component: Vendas },
      { path: 'financeiro/chat', component: Chat },
      { path: 'financeiro/:moduloId', component: Financeiro },
      { path: 'estoque/criar-relatorio', component: EstoqueCriarRelatorio },
      { path: 'estoque/especifico-grupo-conceito', component: EstoqueEspecificoGrupoConceito },
      { path: 'estoque/chat', component: EstoqueChat },
      { path: 'estoque', component: Estoque },
      { path: 'rh', redirectTo: 'rh/analise-candidato' },
      { path: 'rh/analise-candidato', component: AnaliseCandidato },
      { path: 'rh/selecionar-candidato', component: SelecionarCandidato },
      { path: 'rh/repescagem', component: Repescagem },
      { path: 'rh/colaboradores', component: Colaboradores },
      { path: 'ti/seguranca', component: SegurancaTi },
      { path: 'relatorios/historico', component: Historico },
      { path: 'auditoria/historico', component: AuditoriaHistorico },
      { path: 'juntar-excel', component: JuntarExcel },
      { path: 'usuarios', component: Usuarios, canActivate: [adminGuard] },
    ],
  },
  { path: '**', redirectTo: '' },
];
