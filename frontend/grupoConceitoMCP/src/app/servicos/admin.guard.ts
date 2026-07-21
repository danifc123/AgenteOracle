import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { Sessao } from './sessao';

export const adminGuard: CanActivateFn = () => {
  const sessao = inject(Sessao);
  const router = inject(Router);

  if (sessao.administrador()) {
    return true;
  }

  return router.parseUrl('/');
};
