import { HttpClient } from '@angular/common/http';
import { Injectable, computed, effect, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../app-config';
import { Sessao } from '../sessao/sessao';

export interface TokenAmbiente {
  token: string;
  rotulo: string;
  padrao: string;
}

export interface CorAmbienteExibicao extends TokenAmbiente {
  cor: string;
  personalizada: boolean;
}

interface CorAmbiente {
  token: string;
  cor: string;
}

// Todas as variáveis CSS de COR do sistema que são um hex sólido (ver
// `styles.scss` pro valor padrão de cada uma — `padrao` aqui precisa
// ficar em sincronia manual com lá, é só o hex de referência pro
// color-picker antes de o usuário personalizar) — duplicado de propósito
// em `server/auth/cores_ambiente.py::_TOKENS_VALIDOS` (mesma decisão de
// `CoresCategoria`/backend: é uma lista de dado, não compensa acoplar
// front/back só por isso). De fora, de propósito:
// - Tipografia/espaçamento (`--font-*`, `--text-*` etc.) — não é cor, não
//   faz sentido nesta tela.
// - `--color-error-soft`/`--color-warning-soft` — são `rgba(...)` com
//   transparência (fundo suave de aviso/erro), não hex sólido; o
//   `<input type="color">` nativo (`configuracoes-usuario.html`) só
//   aceita/devolve `#rrggbb`, perderia a transparência se deixasse
//   personalizar por aqui. `--color-success-soft` fica de fora do mesmo
//   jeito mesmo sendo hex (referencia `--color-primary-soft`), pra não
//   editar sozinho um alias que os outros dois "-soft" não conseguem
//   acompanhar — os três ficam de fora juntos, por consistência.
export const TOKENS_AMBIENTE: readonly TokenAmbiente[] = [
  { token: '--color-primary', rotulo: 'Cor primária (barra lateral e botões)', padrao: '#1b4332' },
  { token: '--color-primary-dark', rotulo: 'Cor primária escura (hover, estados ativos)', padrao: '#123024' },
  {
    token: '--color-primary-light',
    rotulo: 'Cor primária clara (ícones, indicadores positivos)',
    padrao: '#2f9e58',
  },
  { token: '--color-bg', rotulo: 'Cor de fundo da página', padrao: '#eef6f0' },
  { token: '--color-surface', rotulo: 'Cor de fundo dos cartões', padrao: '#ffffff' },
  { token: '--color-border', rotulo: 'Cor das bordas', padrao: '#dbe7de' },
  { token: '--color-text', rotulo: 'Cor do texto principal', padrao: '#1f2a24' },
  { token: '--color-text-muted', rotulo: 'Cor do texto secundário', padrao: '#5b6b62' },
  { token: '--color-accent', rotulo: 'Cor de destaque', padrao: '#e8871e' },
  { token: '--color-accent-dark', rotulo: 'Cor de destaque escura (hover)', padrao: '#c96f12' },
  { token: '--color-primary-soft', rotulo: 'Cor primária suave (fundos leves)', padrao: '#e3efe7' },
  {
    token: '--color-primary-softer',
    rotulo: 'Cor primária bem suave (fundos muito leves)',
    padrao: '#f2f8f4',
  },
  { token: '--color-error', rotulo: 'Cor de erro', padrao: '#9a2f2f' },
  { token: '--color-warning', rotulo: 'Cor de aviso', padrao: '#b5620a' },
  { token: '--color-success', rotulo: 'Cor de sucesso', padrao: '#2f9e58' },
];

/** Cores de ambiente personalizáveis por usuário (Configurações → "Cores de
 * ambiente") — aberto a QUALQUER usuário, diferente de `CoresCategoria`
 * (só Financeiro): aparência é preferência pessoal, não dado de negócio de
 * módulo nenhum. Aplica direto no `<html>` via CSS custom properties
 * (`document.documentElement.style`), então o efeito é imediato — nenhum
 * componente precisa saber que isso existe, continuam usando
 * `var(--color-primary)` como sempre. Persistido no backend
 * (`cores_ambiente`), pra sobreviver a logout/troca de máquina. */
@Injectable({ providedIn: 'root' })
export class CoresAmbiente {
  private readonly http = inject(HttpClient);
  private readonly sessao = inject(Sessao);

  private readonly personalizadas = signal<Record<string, string>>({});

  readonly listaParaExibir = computed<CorAmbienteExibicao[]>(() => {
    const personalizadas = this.personalizadas();
    return TOKENS_AMBIENTE.map((item) => ({
      ...item,
      cor: personalizadas[item.token] ?? item.padrao,
      personalizada: item.token in personalizadas,
    }));
  });

  constructor() {
    // Reage a login/logout: troca de usuário é só navegação de rota (sem
    // recarregar a página), sem isso as cores do usuário anterior ficariam
    // aplicadas depois de logar com outra conta na mesma aba. Sem gate de
    // módulo de propósito — mesmo bug que `CoresCategoria` já teve
    // (achado do usuário, 2026-09-28): esta tela é pra todo mundo, gatear
    // por módulo geraria toast de erro sozinho pra quem não tem nenhum.
    effect(() => {
      if (this.sessao.token()) {
        this.carregar();
      } else {
        this.personalizadas.set({});
      }
    });

    // Aplica no documento sempre que a lista efetiva mudar — é isso que
    // realmente muda a aparência; o resto da classe só gerencia o dado.
    effect(() => {
      this.aplicarNoDocumento();
    });
  }

  private aplicarNoDocumento(): void {
    const raiz = document.documentElement.style;
    for (const item of this.listaParaExibir()) {
      if (item.personalizada) {
        raiz.setProperty(item.token, item.cor);
      } else {
        raiz.removeProperty(item.token);
      }
    }
  }

  private carregar(): void {
    this.http.get<CorAmbiente[]>(`${MCP_API_BASE_URL}/api/auth/cores-ambiente`).subscribe({
      next: (cores) => {
        this.personalizadas.set(Object.fromEntries(cores.map((item) => [item.token, item.cor])));
      },
      error: () => {
        this.personalizadas.set({});
      },
    });
  }

  aplicarCorLocal(token: string, cor: string): void {
    this.personalizadas.update((atual) => ({ ...atual, [token]: cor }));
  }

  definirCor(token: string, cor: string) {
    return this.http.put<CorAmbiente>(
      `${MCP_API_BASE_URL}/api/auth/cores-ambiente/${encodeURIComponent(token)}`,
      { cor },
    );
  }

  redefinirCor(token: string) {
    return this.http.delete(`${MCP_API_BASE_URL}/api/auth/cores-ambiente/${encodeURIComponent(token)}`);
  }

  removerCorLocal(token: string): void {
    this.personalizadas.update((atual) => {
      const { [token]: _removida, ...resto } = atual;
      return resto;
    });
  }
}
