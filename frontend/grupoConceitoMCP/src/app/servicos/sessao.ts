import { Injectable, signal } from '@angular/core';

const CHAVE_SESSAO = 'sessao:usuario';

export interface DadosSessao {
  token: string;
  usuario: string;
  nome: string;
  papeis: string[];
}

function carregarSessaoSalva(): DadosSessao | null {
  const bruto = localStorage.getItem(CHAVE_SESSAO);
  if (!bruto) {
    return null;
  }
  try {
    return JSON.parse(bruto) as DadosSessao;
  } catch {
    return null;
  }
}

@Injectable({ providedIn: 'root' })
export class Sessao {
  private readonly _dados = signal<DadosSessao | null>(carregarSessaoSalva());

  readonly autenticado = () => this._dados() !== null;
  readonly token = () => this._dados()?.token ?? null;
  readonly nome = () => this._dados()?.nome ?? '';
  readonly papeis = () => this._dados()?.papeis ?? [];

  entrar(dados: DadosSessao): void {
    localStorage.setItem(CHAVE_SESSAO, JSON.stringify(dados));
    this._dados.set(dados);
  }

  sair(): void {
    localStorage.removeItem(CHAVE_SESSAO);
    this._dados.set(null);
  }
}
