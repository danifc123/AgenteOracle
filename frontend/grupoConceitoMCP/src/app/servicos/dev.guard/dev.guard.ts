import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { Sessao } from '../sessao/sessao';

export const devGuard: CanActivateFn = () => {
  const sessao = inject(Sessao);
  const router = inject(Router);

  if (sessao.ehDesenvolvedor()) {
    return true;
  }

  return router.parseUrl('/');
};
