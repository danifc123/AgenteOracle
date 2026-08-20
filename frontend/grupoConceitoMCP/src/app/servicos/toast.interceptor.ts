import {
  HttpContextToken,
  HttpErrorResponse,
  HttpInterceptorFn,
  HttpResponse,
} from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, tap, throwError } from 'rxjs';
import { mensagemErro } from './mensagens-erro';
import { Toasts } from './toasts';

/** Mensagem de sucesso customizada pra essa requisição — sem isso, POST/PUT/
 * PATCH/DELETE bem-sucedidos usam a mensagem genérica abaixo. Útil quando a
 * tela quer um texto mais específico ("Localização salva.") sem precisar
 * desligar o toast automático e chamar `Toasts` na mão. */
export const TOAST_MENSAGEM_SUCESSO = new HttpContextToken<string | null>(() => null);

/** Desliga o toast automático (sucesso E erro) pra essa requisição — pra
 * quando a tela precisa de controle total (ex: mensagem de sucesso que
 * depende do corpo da resposta, não dá pra decidir antes de mandar). */
export const TOAST_DESATIVADO = new HttpContextToken<boolean>(() => false);

const MENSAGEM_SUCESSO_PADRAO = 'Ação realizada com sucesso.';
const METODOS_MUTACAO = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

/** Toast automático pra toda resposta da API — erro de qualquer requisição
 * vira toast (reaproveitando `{"erro": "..."}` que o backend já devolve de
 * forma consistente), e toda ação que muda dado (POST/PUT/PATCH/DELETE) bem-
 * sucedida também vira toast. GET nunca gera toast de sucesso (navegação/
 * carregamento de tela não é uma "ação" que precise de confirmação — só
 * gerar ruído).
 *
 * Login (`/api/auth/login`) fica de fora — já tem sua própria mensagem de
 * erro inline (login.ts, com contagem regressiva de bloqueio por
 * tentativas). Erro 401 também fica de fora — o `authInterceptor` já
 * redireciona pro login nesse caso, um toast a mais só atrapalharia. */
export const toastInterceptor: HttpInterceptorFn = (request, next) => {
  const toasts = inject(Toasts);

  const desativado = request.context.get(TOAST_DESATIVADO);
  const ehLogin = request.url.endsWith('/api/auth/login');
  const ehMutacao = METODOS_MUTACAO.has(request.method);

  return next(request).pipe(
    tap((evento) => {
      if (desativado || ehLogin || !ehMutacao || !(evento instanceof HttpResponse)) {
        return;
      }
      toasts.sucesso(request.context.get(TOAST_MENSAGEM_SUCESSO) ?? MENSAGEM_SUCESSO_PADRAO);
    }),
    catchError((erro: HttpErrorResponse) => {
      if (!desativado && !ehLogin && erro.status !== 401) {
        toasts.erro(mensagemErro(erro, 'Não foi possível completar a ação.'));
      }
      return throwError(() => erro);
    }),
  );
};
