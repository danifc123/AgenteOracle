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

// Só as variáveis CSS que fazem sentido personalizar por usuário (visual
// pessoal, ver `styles.scss` pro valor padrão de cada uma) — duplicado de
// propósito em `server/auth/cores_ambiente.py::_TOKENS_VALIDOS` (mesma
// decisão de `CoresCategoria`/backend: são 2 linhas, não compensa acoplar
// front/back só por isso).
export const TOKENS_AMBIENTE: readonly TokenAmbiente[] = [
  { token: '--color-primary', rotulo: 'Cor primária (barra lateral e botões)', padrao: '#1b4332' },
  { token: '--color-accent', rotulo: 'Cor de destaque', padrao: '#e8871e' },
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
