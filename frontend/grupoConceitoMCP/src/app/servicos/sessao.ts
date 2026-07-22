import { Injectable, signal } from '@angular/core';

const CHAVE_SESSAO = 'sessao:usuario';

export interface DadosSessao {
  token: string;
  usuario: string;
  nome: string;
  foto: string | null;
  papeis: string[];
  administrador: boolean;
  modulos: string[];
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
  readonly foto = () => this._dados()?.foto ?? null;
  readonly papeis = () => this._dados()?.papeis ?? [];
  readonly administrador = () => this._dados()?.administrador ?? false;
  readonly modulos = () => this._dados()?.modulos ?? [];

  entrar(dados: DadosSessao): void {
    localStorage.setItem(CHAVE_SESSAO, JSON.stringify(dados));
    this._dados.set(dados);
  }

  /** Autoatendimento: mescla nome/foto atualizados na sessão já logada, sem
   * precisar relogar (usado depois de um PATCH /api/auth/perfil). */
  atualizarPerfil(dados: Partial<Pick<DadosSessao, 'nome' | 'foto'>>): void {
    const atual = this._dados();
    if (!atual) {
      return;
    }
    const novo = { ...atual, ...dados };
    localStorage.setItem(CHAVE_SESSAO, JSON.stringify(novo));
    this._dados.set(novo);
  }

  sair(): void {
    localStorage.removeItem(CHAVE_SESSAO);
    this._dados.set(null);
  }
}
