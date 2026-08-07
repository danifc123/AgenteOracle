import { HttpClient } from '@angular/common/http';
import { Injectable, computed, effect, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../app-config';
import { CategoriaCor } from '../dadosRelatorios/categoria-cor';
import { COR_CATEGORIA_PADRAO, MODULOS_FINANCEIRO } from '../dadosRelatorios/modulos-financeiro';
import { Sessao } from './sessao';

export interface CategoriaCorExibicao {
  categoria: string;
  cor: string;
  personalizada: boolean;
}

/** Cores de categoria de relatório personalizáveis por usuário (Configurações
 * → "Cores das categorias"). Categorias sem personalização usam
 * `COR_CATEGORIA_PADRAO`. Persistido no backend (`categoria_cores`). */
@Injectable({ providedIn: 'root' })
export class CoresCategoria {
  private readonly http = inject(HttpClient);
  private readonly sessao = inject(Sessao);

  private readonly personalizadas = signal<Record<string, string>>({});

  readonly categorias = computed(() => {
    const vistas = new Set<string>();
    const lista: string[] = [];
    for (const modulo of MODULOS_FINANCEIRO) {
      for (const rotina of modulo.rotinas) {
        if (!vistas.has(rotina.categoria)) {
          vistas.add(rotina.categoria);
          lista.push(rotina.categoria);
        }
      }
    }
    return lista;
  });

  readonly listaParaExibir = computed<CategoriaCorExibicao[]>(() => {
    const personalizadas = this.personalizadas();
    return this.categorias().map((categoria) => ({
      categoria,
      cor: personalizadas[categoria] ?? COR_CATEGORIA_PADRAO,
      personalizada: categoria in personalizadas,
    }));
  });

  constructor() {
    // Reage a login/logout: como a troca de usuário é só navegação de rota
    // (sem recarregar a página), sem isso o serviço ficaria com as cores do
    // usuário anterior em memória depois de logar com outra conta na mesma aba.
    effect(() => {
      if (this.sessao.token()) {
        this.carregar();
      } else {
        this.personalizadas.set({});
      }
    });
  }

  private carregar(): void {
    this.http.get<CategoriaCor[]>(`${MCP_API_BASE_URL}/api/financeiro/categorias/cores`).subscribe({
      next: (cores) => {
        this.personalizadas.set(
          Object.fromEntries(cores.map((item) => [item.categoria, item.cor])),
        );
      },
      error: () => {
        this.personalizadas.set({});
      },
    });
  }

  aplicarCorLocal(categoria: string, cor: string): void {
    this.personalizadas.update((atual) => ({ ...atual, [categoria]: cor }));
  }

  definirCor(categoria: string, cor: string) {
    return this.http.put<CategoriaCor>(
      `${MCP_API_BASE_URL}/api/financeiro/categorias/cores/${encodeURIComponent(categoria)}`,
      { cor },
    );
  }

  obterCor(categoria: string): string {
    return this.personalizadas()[categoria] ?? COR_CATEGORIA_PADRAO;
  }

  redefinirCor(categoria: string) {
    return this.http.delete(
      `${MCP_API_BASE_URL}/api/financeiro/categorias/cores/${encodeURIComponent(categoria)}`,
    );
  }

  removerCorLocal(categoria: string): void {
    this.personalizadas.update((atual) => {
      const { [categoria]: _removida, ...resto } = atual;
      return resto;
    });
  }
}
