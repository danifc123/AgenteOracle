import { Injectable, signal } from '@angular/core';

const CHAVE_SESSAO = 'sessao:usuario';

/** Nome amigável de cada módulo conhecido — usado em qualquer lugar que
 * precise mostrar o módulo pro usuário (seletor de auditoria, seletor de
 * home do desenvolvedor, etc). Módulo sem entrada aqui cai no próprio slug
 * (fallback razoável até alguém lembrar de cadastrar o rótulo). */
const ROTULOS_MODULO: Record<string, string> = {
  financeiro: 'Financeiro',
  estoque: 'Estoque',
};

export function rotuloModulo(modulo: string): string {
  return ROTULOS_MODULO[modulo] ?? modulo;
}

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
  /** Diferente de `administrador` (verdadeiro pra qualquer papel admin, ex:
   * `financeiro_admin`), aqui é só o papel `desenvolvedor` especificamente —
   * espelha `eh_desenvolvedor` do backend (`tools/auth/papeis.py`). */
  readonly ehDesenvolvedor = () => this._dados()?.papeis.includes('desenvolvedor') ?? false;

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
