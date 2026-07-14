import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { Sessao } from './sessao';

export const authGuard: CanActivateFn = () => {
  const sessao = inject(Sessao);
  const router = inject(Router);

  if (sessao.autenticado()) {
    return true;
  }

  return router.parseUrl('/login');
};
