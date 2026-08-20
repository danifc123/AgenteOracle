import { Injectable, inject, signal } from '@angular/core';
import { Router } from '@angular/router';

const CHAVE_SESSAO = 'sessao:usuario';

/** Nome amigável de cada módulo conhecido — usado em qualquer lugar que
 * precise mostrar o módulo pro usuário (seletor de auditoria, seletor de
 * home do desenvolvedor, etc). Módulo sem entrada aqui cai no próprio slug
 * (fallback razoável até alguém lembrar de cadastrar o rótulo). */
const ROTULOS_MODULO: Record<string, string> = {
  financeiro: 'Financeiro',
  estoque: 'Estoque',
  rh: 'RH',
  ti: 'TI',
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

function parseSessao(bruto: string | null): DadosSessao | null {
  if (!bruto) {
    return null;
  }
  try {
    return JSON.parse(bruto) as DadosSessao;
  } catch {
    return null;
  }
}

function carregarSessaoSalva(): DadosSessao | null {
  return parseSessao(localStorage.getItem(CHAVE_SESSAO));
}

/** Lê o `exp` (epoch em segundos) de dentro do JWT sem validar assinatura —
 * só pra saber QUANDO agendar a expulsão no cliente; a validação de
 * verdade continua no backend (`tools/auth/token.py::verificar_token`), que
 * rejeita o token de qualquer forma depois desse horário. */
function expiracaoEmMs(token: string): number | null {
  const payloadBase64 = token.split('.')[1];
  if (!payloadBase64) {
    return null;
  }
  try {
    const normalizado = payloadBase64.replace(/-/g, '+').replace(/_/g, '/');
    const preenchido = normalizado.padEnd(normalizado.length + ((4 - (normalizado.length % 4)) % 4), '=');
    const payload = JSON.parse(atob(preenchido));
    return typeof payload.exp === 'number' ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}

@Injectable({ providedIn: 'root' })
export class Sessao {
  private readonly router = inject(Router);
  private readonly _dados = signal<DadosSessao | null>(carregarSessaoSalva());
  private timeoutExpiracao?: ReturnType<typeof setTimeout>;

  /** Chamada no login, ao carregar a sessão salva e ao sincronizar entre
   * abas — sempre que o token em memória muda, reagenda a expulsão
   * automática pro horário exato em que ele expira (8h de jornada de
   * trabalho, `AUTH_TOKEN_HORAS` no backend), mesmo que o usuário fique a
   * aba inteira sem clicar em nada (sem isso, só descobriria o vencimento
   * na próxima chamada à API, que devolveria 401). */
  private agendarExpiracao(token: string | null): void {
    clearTimeout(this.timeoutExpiracao);
    if (!token) {
      return;
    }
    const expiraEm = expiracaoEmMs(token);
    if (expiraEm === null) {
      return;
    }
    this.timeoutExpiracao = setTimeout(() => this.expulsar(), Math.max(expiraEm - Date.now(), 0));
  }

  // expulsar só é usada pelo timeout agendado dentro de agendarExpiracao,
  // logo depois dela.
  private expulsar(): void {
    this.sair();
    this.router.navigateByUrl('/login');
  }

  /** Sincroniza sessão entre abas: o evento `storage` só dispara nas abas
   * que NÃO fizeram a mudança, então isso é o que permite uma aba deslogada
   * "expulsar" as outras na hora, sem precisar recarregar a página — antes
   * disso, uma segunda aba continuava autenticada (com o token antigo em
   * memória) até o usuário atualizar a tela manualmente. */
  constructor() {
    window.addEventListener('storage', (evento) => this.sincronizarEntreAbas(evento));
    this.agendarExpiracao(this.token());
  }

  // sincronizarEntreAbas só é usada pelo listener registrado no
  // construtor, logo depois dele.
  private sincronizarEntreAbas(evento: StorageEvent): void {
    if (evento.key !== CHAVE_SESSAO) {
      return;
    }
    const novosDados = parseSessao(evento.newValue);
    this._dados.set(novosDados);
    this.agendarExpiracao(novosDados?.token ?? null);
    if (!novosDados) {
      this.router.navigateByUrl('/login');
    }
  }

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

  entrar(dados: DadosSessao): void {
    localStorage.setItem(CHAVE_SESSAO, JSON.stringify(dados));
    this._dados.set(dados);
    this.agendarExpiracao(dados.token);
  }

  sair(): void {
    clearTimeout(this.timeoutExpiracao);
    localStorage.removeItem(CHAVE_SESSAO);
    this._dados.set(null);
  }
}
