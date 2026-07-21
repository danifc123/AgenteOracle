import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';
import { Sessao } from './sessao';

export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const sessao = inject(Sessao);
  const router = inject(Router);

  const token = sessao.token();
  const ehLogin = request.url.endsWith('/api/auth/login');
  const requisicao = token && !ehLogin
    ? request.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
    : request;

  return next(requisicao).pipe(
    catchError((erro: HttpErrorResponse) => {
      if (erro.status === 401 && !ehLogin) {
        sessao.sair();
        router.navigateByUrl('/login');
      }
      return throwError(() => erro);
    })
  );
};
