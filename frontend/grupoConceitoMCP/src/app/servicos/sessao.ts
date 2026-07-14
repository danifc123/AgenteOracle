import { Injectable, signal } from '@angular/core';

const CHAVE_SESSAO = 'sessao:autenticado';

@Injectable({ providedIn: 'root' })
export class Sessao {
  private readonly _autenticado = signal(localStorage.getItem(CHAVE_SESSAO) === 'true');
  readonly autenticado = this._autenticado.asReadonly();

  entrar(): void {
    localStorage.setItem(CHAVE_SESSAO, 'true');
    this._autenticado.set(true);
  }

  sair(): void {
    localStorage.removeItem(CHAVE_SESSAO);
    this._autenticado.set(false);
  }
}
